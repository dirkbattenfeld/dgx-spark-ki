import logging
import os
import traceback
import uuid
from typing import Any, List, TypeVar, Generator

from qdrant_client.models import (
    PointStruct, Filter, FieldCondition, MatchValue, Distance, VectorParams
)

from applications.rag.pipelines.rag_ingestion.steps.configs import StoreConfig
from applications.rag.pipelines.rag_ingestion.steps.models import EmbedOutput, IngestionResult

logger = logging.getLogger(__name__)

T = TypeVar("T")

def _chunk_batch(data: List[T], batch_size: int) -> Generator[List[T], None, None]:
    """Hilfsfunktion zum Zerlegen einer Liste in Batches definierter Größe."""
    size = max(1, batch_size)
    for i in range(0, len(data), size):
        yield data[i : i + size]

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
        logger.info(f"🆕 [Qdrant] Kollektion '{config.collection_name}' automatisch angelegt.")
    
    # 2. Parent-Kollektion erstellen, falls sie fehlt
    if parent_col not in existing:
        await client.create_collection(
            collection_name=parent_col, 
            vectors_config={}  # Reiner Metadaten/Payload-Store
        )
        logger.info(f"🆕 [Qdrant] Parent-Kollektion '{parent_col}' automatisch angelegt.")

async def store_action(
    embed_output: EmbedOutput, 
    qdrant_service: Any, 
    config: StoreConfig
) -> IngestionResult:
    """
    Asynchrone Action: Bereitet Payloads vor, bereinigt Altbestände (Idempotenz)
    und schreibt Chunks & Parents gebatcht via Qdrant SDK.
    """

    parent_stored = 0
    child_stored = 0
    errors: List[str] = []
    
    doc_id = embed_output.source_path
    filename = os.path.basename(doc_id)
    
    qdrant_client = qdrant_service.client
    parent_col = config.parent_collection_name or f"{config.collection_name}_parents"

    # Liest optional batch_size_child/parent aus der config aus, falls dort definiert
    b_size_child = getattr(config, "batch_size_child", 400)
    b_size_parent = getattr(config, "batch_size_parent", 64)

    try:
        # 1. Kollektionen sicherstellen
        await _ensure_collections(qdrant_client, config)
        
        # 2. Idempotenz-Schutz: Altbestände löschen
        purge_filter = Filter(
            must=[FieldCondition(key="source_path", match=MatchValue(value=doc_id))]
        )
        await qdrant_client.delete(collection_name=config.collection_name, points_selector=purge_filter)
        await qdrant_client.delete(collection_name=parent_col, points_selector=purge_filter)
        
        # 3. Parent-Chunks vorbereiten und gebatcht speichern
        if embed_output.parent_chunks:
            p_points = []
            for p_idx, p in enumerate(embed_output.parent_chunks):
                if not p.id or not str(p.id).strip():
                    err_msg = (
                        f"🛑 [CRITICAL BUG] Parent-Chunk bei Index {p_idx} hat eine ungültige oder leere ID! "
                        f"Datei: {filename} | Text-Snippet: '{p.text[:60]}...'"
                    )
                    logger.error(err_msg)
                    raise ValueError(err_msg)

                p_points.append(
                    PointStruct(
                        id=str(p.id), 
                        vector={}, 
                        payload={"text": p.text, "source_path": doc_id, **p.meta}
                    )
                )
            
            # Batching für Parent Chunks
            total_p_batches = (len(p_points) + b_size_parent - 1) // max(1, b_size_parent)
            for b_idx, batch in enumerate(_chunk_batch(p_points, b_size_parent), start=1):
                try:
                    await qdrant_client.upsert(collection_name=parent_col, points=batch)
                    parent_stored += len(batch)
                    logger.debug(f"📦 [Qdrant] Parent-Batch {b_idx}/{total_p_batches} ({len(batch)} Points) gespeichert.")
                except Exception as batch_err:
                    err_detail = (
                        f"❌ [Qdrant Error] Fehler beim Schreiben des Parent-Batches {b_idx}/{total_p_batches} "
                        f"in '{parent_col}' (Batch-Größe: {len(batch)}): {str(batch_err)}\n"
                        f"Stacktrace:\n{traceback.format_exc()}"
                    )
                    logger.error(err_detail)
                    errors.append(err_detail)
                    raise RuntimeError(err_detail) from batch_err

        # 4. Child-Chunks vorbereiten und gebatcht speichern
        child_points = []
        for idx, ec in enumerate(embed_output.embedded_chunks):
            if not ec.chunk.parent_id or not str(ec.chunk.parent_id).strip():
                err_msg = (
                    f"🛑 [CRITICAL BUG] Child-Chunk bei Index {idx} hat keine verknüpfte parent_doc_id! "
                    f"Datei: {filename} | Text-Snippet: '{ec.chunk.text[:60]}...'"
                )
                logger.error(err_msg)
                raise ValueError(err_msg)

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

        if child_points:
            # Batching für Child Chunks
            total_c_batches = (len(child_points) + b_size_child - 1) // max(1, b_size_child)
            for b_idx, batch in enumerate(_chunk_batch(child_points, b_size_child), start=1):
                try:
                    await qdrant_client.upsert(collection_name=config.collection_name, points=batch)
                    child_stored += len(batch)
                    logger.debug(f"📦 [Qdrant] Child-Batch {b_idx}/{total_c_batches} ({len(batch)} Points) gespeichert.")
                except Exception as batch_err:
                    err_detail = (
                        f"❌ [Qdrant Error] Fehler beim Schreiben des Child-Batches {b_idx}/{total_c_batches} "
                        f"in '{config.collection_name}' (Batch-Größe: {len(batch)}): {str(batch_err)}\n"
                        f"Stacktrace:\n{traceback.format_exc()}"
                    )
                    logger.error(err_detail)
                    errors.append(err_detail)
                    raise RuntimeError(err_detail) from batch_err

        logger.info(f"💾 [Qdrant] '{filename}' synchronisiert. {child_stored} Childs, {parent_stored} Parents gespeichert.")
        status = "success"

    except Exception as e:
        status = "failed"
        err_msg = f"💥 [FATAL ERROR] Ingestion abgebrochen für '{filename}': {str(e)}\nStacktrace:\n{traceback.format_exc()}"
        logger.error(err_msg)
        if err_msg not in errors:
            errors.append(err_msg)

    pipeline_metrics = {
        "chunks_stored": child_stored,
        "parent_chunks_stored": parent_stored,
        "collection": config.collection_name,
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
        extras=pipeline_metrics
    )
