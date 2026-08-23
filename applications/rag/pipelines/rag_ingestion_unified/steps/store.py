import os
import uuid
import logging
from typing import Any

from qdrant_client.models import (
    PointStruct, Filter, FieldCondition, MatchValue, Distance, VectorParams
)

from applications.rag.pipelines.rag_ingestion.steps.configs import StoreConfig
from applications.rag.pipelines.rag_ingestion.steps.models import EmbedOutput, IngestionResult
from libs.streampipe.observability import trace_action

logger = logging.getLogger("Pipeline.StoreQdrant")

async def _ensure_collections(client: Any, config: StoreConfig):
    """Prüft asynchron, ob Kollektionen existieren, und legt sie an."""
    parent_col = config.parent_collection_name or f"{config.collection_name}_parents"
    
    # Hole existierende Kollektionen vom Server
    collections_response = await client.get_collections()
    existing = [c.name for c in collections_response.collections]
    
    # 1. Haupt-Kollektion (Child-Chunks) erstellen, falls sie fehlt
    if config.collection_name not in existing:
        dist = Distance.COSINE if config.distance == "Cosine" else Distance.DOT
        await client.create_collection(
            collection_name=config.collection_name,
            vectors_config={"dense": VectorParams(size=config.vector_size, distance=dist)}
        )
        print(f"🆕 [Qdrant] Kollektion '{config.collection_name}' automatisch angelegt.")
    
    # 2. Parent-Kollektion erstellen, falls sie fehlt
    if parent_col not in existing:
        await client.create_collection(
            collection_name=parent_col, 
            vectors_config={}  # Reiner Metadaten/Payload-Store
        )
        print(f"🆕 [Qdrant] Parent-Kollektion '{parent_col}' automatisch angelegt.")
        

@trace_action(step_name="store")        
async def store_action(
    embed_output: EmbedOutput, 
    qdrant_service: Any, 
    config: StoreConfig
) -> IngestionResult:
    """
    Asynchrone Action: Bereitet Payloads vor, bereinigt Altbestände (Idempotenz)
    und schreibt Chunks & Parents parallel via DGX-SDK in Qdrant.
    """
    errors = []
    parent_stored = 0
    child_stored = 0
    
    doc_id = embed_output.source_path
    filename = os.path.basename(doc_id)
    
    # Hole den vorkonfigurierten AsyncQdrantClient aus der Property deines SDKs
    qdrant_client = qdrant_service.client
    parent_col = config.parent_collection_name or f"{config.collection_name}_parents"
    
    try:
        await _ensure_collections(qdrant_client, config)
        
        # 1. Idempotenz-Schutz: Lösche alte Bestände dieses Dokuments, falls vorhanden (Purge-Before-Write)
        # Das fängt geänderte Dokumente sauber ab!
        purge_filter = Filter(
            must=[FieldCondition(key="source_path", match=MatchValue(value=doc_id))]
        )
        await qdrant_client.delete(collection_name=config.collection_name, points_selector=purge_filter)
        await qdrant_client.delete(collection_name=parent_col, points_selector=purge_filter)
        
        # 2. Parent-Chuncks vorbereiten
        if embed_output.parent_chunks:
            p_points = []
            for p_idx, p in enumerate(embed_output.parent_chunks):
                
                # SCHARFE VALIDIERUNG: Ist die ID da und nicht nur Whitespace?
                if not p.id or not str(p.id).strip():
                    error_msg = (
                        f"🛑 [CRITICAL BUG] Parent-Chunk bei Index {p_idx} hat eine ungültige oder leere ID! "
                        f"Datei: {filename} | Text-Snippet: '{p.text[:60]}...'"
                    )
                    print(error_msg)
                    raise ValueError(error_msg)  # Lässt die Pipeline für dieses Doc kontrolliert crashen

                p_points.append(
                    PointStruct(
                        id=str(p.id), 
                        vector={}, 
                        payload={"text": p.text, "source_path": doc_id, **p.meta}
                    )
                )
            
            await qdrant_client.upsert(collection_name=parent_col, points=p_points)
            parent_stored = len(p_points)      

        # 3. Child-Chunks vorbereiten (Nutze deterministische IDs für Idempotenz)
        child_points = []
        for idx, ec in enumerate(embed_output.embedded_chunks):
            try:
                # SCHARFE VALIDIERUNG FÜR DEN LINK: Hat das Child eine Parent-ID?
                if not ec.chunk.parent_id or not str(ec.chunk.parent_id).strip():
                    error_msg = (
                        f"🛑 [CRITICAL BUG] Child-Chunk bei Index {idx} hat keine verknüpfte parent_doc_id! "
                        f"Datei: {filename} | Text-Snippet: '{ec.chunk.text[:60]}...'"
                    )
                    print(error_msg)
                    raise ValueError(error_msg)

                payload = {
                    "text": ec.chunk.text,
                    "source_path": doc_id,
                    "parent_doc_id": str(ec.chunk.parent_id),
                    **ec.chunk.meta
                }
                if ec.context_preamble:
                    payload["context_preamble"] = ec.context_preamble

                deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{idx}"))
                child_points.append(
                    PointStruct(id=deterministic_id, vector={"dense": ec.dense_vector}, payload=payload)
                )
            except Exception as e:
                # Wir wollen, dass auch innere Fehler die Pipeline stoppen, falls gewünscht
                errors.append(f"Point-Creation-Error bei Index {idx}: {e}")
                raise

        # 4. Daten-Ingest ausführen
        if child_points:
            await qdrant_client.upsert(collection_name=config.collection_name, points=child_points)
            child_stored = len(child_points)
            
        print(f"💾 [Qdrant] '{filename}' synchronisiert. {child_stored} Childs, {parent_stored} Parents gespeichert.")

    except Exception as global_exc:
        errors.append(f"Kritischer Qdrant-Speicherfehler: {global_exc}")
        print(f"💥 Fehler beim Ingest in Qdrant für {filename}: {global_exc}")

    status = "success" if not errors else "error"

    # Zusammenbau der Metriken für das zentrale JSON-Logging im Decorator
    pipeline_metrics = {
        "chunks_stored": child_stored,
        "parent_chunks_stored": parent_stored,
        "collection": config.collection_name,
        "errors_count": len(errors),
        "status": status
    }

    return IngestionResult(
        source_path=str(doc_id),
        chunks_total=len(embed_output.embedded_chunks),
        chunks_stored=child_stored,
        parent_chunks_total=len(embed_output.parent_chunks),
        parent_chunks_stored=parent_stored,
        collection_name=config.collection_name,
        errors=errors,
        status=status,
        extras=pipeline_metrics  # <-- Für das automatische Tracing im Decorator
    )

