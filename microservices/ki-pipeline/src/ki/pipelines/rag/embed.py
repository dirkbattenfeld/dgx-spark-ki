from typing import List, Dict, Any, ClassVar, Optional
from pydantic import BaseModel, Field
from dataclasses import dataclass
import httpx

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent
from ki.pipelines.rag.chunk import ChunkedDocument 

class EmbeddedChunk(BaseModel):
    chunk: Any 
    dense_vector: List[float]
    sparse_vector: Dict[int, float] = Field(default_factory=dict)
    context_preamble: Optional[str] = None

class EmbedOutput(BaseModel):
    source_path: Any
    embedded_chunks: List[EmbeddedChunk]
    parent_chunks: List[Any]

class EmbedConfig(BaseModel):
    batch_size: int = 32
    normalize: bool = True
    return_sparse: bool = False

@dataclass
class EmbedRunContext(BaseRunContext[EmbedConfig]):
    component_name: str
    config: EmbedConfig

@component_registry.register('embed_bge')
class EmbedBGE(BaseComponent):
    CONFIG_CLASS: ClassVar[type] = EmbedConfig
    INPUT_CLASS: ClassVar[type] = ChunkedDocument
    OUTPUT_CLASS: ClassVar[type] = EmbedOutput
    RUN_CONTEXT_CLASS: ClassVar[type] = EmbedRunContext

    def run(self, data: ChunkedDocument, *, component_ctx: EmbedRunContext, global_ctx: GlobalRunContext) -> EmbedOutput:
        run_logger = global_ctx.run_logger
        cfg = component_ctx.config
        
        # Fachlogik: Texte mit Preamble zusammensetzen
        texts = []
        for chunk in data.chunks:
            preamble = chunk.meta.get("context_preamble", "")
            if preamble:
                texts.append(f"{preamble}\n\n{chunk.text}")
            else:
                texts.append(chunk.text)

        run_logger.info(f"Sende {len(texts)} Chunks an Infinity-Service ({global_ctx.infra.infinity_url}).")

        with httpx.Client(base_url=global_ctx.infra.infinity_url, timeout=120.0) as client:
            # 1. Dense
            res_dense = client.post("/embeddings", json={"model": global_ctx.infra.MODEL_EMBEDDING, "input": texts})
            res_dense.raise_for_status()
            dense_data = res_dense.json()["data"]

            # 2. Sparse (Exakte Logik mit Key-Konvertierung zu int)
            sparse_data = None
            if cfg.return_sparse:
                try:
                    res_sparse = client.post("/embeddings", json={
                        "model": cfg.model_name, "input": texts, "embedding_type": "sparse"
                    })
                    res_sparse.raise_for_status()
                    sparse_data = res_sparse.json()["data"]
                except Exception as e:
                    run_logger.warning(f"Sparse-Endpunkt nicht verfügbar: {e}")

        embedded_chunks = []
        for i, chunk in enumerate(data.chunks):
            dense_vec = dense_data[i]["embedding"]
            sparse_vec = {}
            if sparse_data:
                raw_sparse = sparse_data[i]["embedding"]
                sparse_vec = {int(k): float(v) for k, v in raw_sparse.items()}
            
            embedded_chunks.append(EmbeddedChunk(
                chunk=chunk,
                dense_vector=dense_vec,
                sparse_vector=sparse_vec,
                context_preamble=chunk.meta.get("context_preamble")
            ))

        return EmbedOutput(
            source_path=data.source.source_path,
            embedded_chunks=embedded_chunks,
            parent_chunks=data.parent_chunks
        )
