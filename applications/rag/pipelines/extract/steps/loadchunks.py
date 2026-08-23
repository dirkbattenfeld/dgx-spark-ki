import os
import yaml
from typing import Any, List

from applications.rag.pipelines.extract.configs import EmptyConfig
from applications.rag.pipelines.rag_ingestion.steps.models import Chunk, ChunkedDocument, ParentChunk, RawDocument, ExtractInput
from libs.streampipe.observability import trace_action


# --- Die eigentliche Action ---

@trace_action(step_name="load_chunks")
async def loadchunks_action(extract_input: ExtractInput, storage_client: Any, config: EmptyConfig) -> ChunkedDocument:
    """
    Lädt bereits existierende Chunks aus einer YAML-Datei via StorageClient
    und bereitet sie als ChunkedDocument für die Extraktionspipeline vor.
    """
    filename = os.path.basename(extract_input.source_path)
    print(f"🔄 [LoadChunks] Lade existierende Chunks aus Datei: {filename}...")
    
    # 1. Datei über den StorageClient einlesen und parsen
    yaml_content_str = storage_client.read(extract_input.source_path)
    data = yaml.safe_load(yaml_content_str) or {}
    
    # Da es eine Liste ist, bleibt die originale Reihenfolge exakt erhalten
    parents_list = data.get("parents", [])
    
    chunks: List[Chunk] = []
    parent_chunks: List[ParentChunk] = []
    
    # 2. Direkt über die Liste der Chunks iterieren
    for chunk_data in parents_list:
        if not chunk_data:
            continue
            
        p_id = chunk_data.get("id", "")
        text = chunk_data.get("text", "")
        meta = chunk_data.get("meta", {})
        
        # ParentChunk erstellen
        parent_chunks.append(
            ParentChunk(
                id=p_id,
                text=text,
                meta=meta
            )
        )
        
        # Chunk (Child) parallel befüllen für die Abwärtskompatibilität
        chunks.append(
            Chunk(
                text=text,
                meta=meta,
                parent_id=p_id
            )
        )
        
    # 3. RawDocument "on-the-fly" mit leeren Standardwerten bauen.
    # Der übergebene source_path der YAML wird als json_path eingetragen.
    raw_doc = RawDocument(
        source_path="",               # Leer, da Docling-Schritt übersprungen
        markdown_content="",          # Leer
        json_path=extract_input.source_path, # Pfad zur YAML-Datei
        metadata={},                  # Leeres Dict
        status="success",
        extras={}
    )
    
    status = "success" if parent_chunks else "error"
    
    # 4. Metriken im extras-Dict sammeln
    pipeline_metrics = {
        "total_parents": len(parent_chunks),
        "total_children": len(chunks),
        "status": status,
        "loaded_from": extract_input.source_path
    }
    
    return ChunkedDocument(
        source=raw_doc,
        chunks=chunks,
        parent_chunks=parent_chunks,
        status=status,
        extras=pipeline_metrics
    )
    
