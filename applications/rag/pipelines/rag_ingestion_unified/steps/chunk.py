# --- Step 2: chunk ---- 
import os
from typing import Any
from applications.rag.pipelines.rag_ingestion.steps.configs import ChunkConfig
from applications.rag.pipelines.rag_ingestion.steps.models import Chunk, ChunkedDocument, ParentChunk, RawDocument
from libs.streampipe.observability import trace_action

@trace_action(step_name="chunk")
async def chunk_action(raw_doc: RawDocument, docling_client: Any, config: ChunkConfig) -> ChunkedDocument:
    filename = os.path.basename(raw_doc.source_path)
    print(f"🔄 [Chunk] Leite extrahiertes Dokument weiter: {filename}...")
    
    res = await docling_client.call_async(
        endpoint_name="chunk",
        json_path=raw_doc.json_path, 
        source_path=raw_doc.source_path,
        config=config.model_dump(exclude={"extras"})
    )
    
    # Parsen der API-Antwort
    api_children = res.get("children", [])
    api_parents = res.get("parents", [])
    
    chunks = [Chunk(text=c.get("text", ""), meta=c.get("meta", {}), parent_id=c.get("parent_id")) for c in api_children]
    parents = [ParentChunk(id=p.get("id", ""), text=p.get("text", ""), meta=p.get("meta", {})) for p in api_parents]
    
    status = "success" if res else "error"
    api_metadata = res.get("metadata", {})

    # Bündeln aller Metriken direkt im extras-Dictionary
    pipeline_metrics = {
        "total_parents": api_metadata.get("total_parents", len(parents)),
        "total_children": api_metadata.get("total_children", len(chunks)),
        "status": status
    }
    
    return ChunkedDocument(
        source=raw_doc,
        chunks=chunks,
        parent_chunks=parents,
        status=status,
        extras=pipeline_metrics  
    )
