import httpx
import time
from typing import List, Dict, ClassVar
from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.rag_request.questionselector import QueryInput

class EmbeddedQuery(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    query: str
    dense_vector: List[float]
    sparse_vector: Dict[int, float] = Field(default_factory=dict)

# --- Komponente ---
class QueryEmbedConfig(BaseModel):
    return_sparse: bool = False

@dataclass
class QueryEmbedRunContext(BaseRunContext[QueryEmbedConfig]):
    component_name: str
    config: QueryEmbedConfig

@component_registry.register('embed_query')
class EmbedQuery(BaseComponent):
    CONFIG_CLASS: ClassVar[type] = QueryEmbedConfig
    INPUT_CLASS: ClassVar[type] = QueryInput
    OUTPUT_CLASS: ClassVar[type] = EmbeddedQuery
    RUN_CONTEXT_CLASS: ClassVar[type] = QueryEmbedRunContext

    def run(self, data: QueryInput, *, component_ctx: QueryEmbedRunContext, global_ctx: GlobalRunContext) -> EmbeddedQuery:
        run_logger = global_ctx.run_logger
        cfg = component_ctx.config
        start = time.time()

        with httpx.Client(base_url=global_ctx.infra.infinity_url, timeout=30.0) as client:
            # Dense Embedding
            resp = client.post("/embeddings", json={"model": global_ctx.infra.MODEL_EMBEDDING, "input": [data.query]})
            resp.raise_for_status()
            dense_vector = resp.json()["data"][0]["embedding"]

            # Sparse Embedding
            sparse_vector = {}
            if cfg.return_sparse:
                try:
                    sresp = client.post("/embeddings", json={
                        "model": cfg.model_name, "input": [data.query], "embedding_type": "sparse"
                    })
                    sresp.raise_for_status()
                    raw = sresp.json()["data"][0]["embedding"]
                    sparse_vector = {int(k): float(v) for k, v in raw.items()}
                except Exception as e:
                    run_logger.warning(f"Sparse-Embedding nicht verfügbar: {e}")

        return EmbeddedQuery(
            query=data.query,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector
        )
