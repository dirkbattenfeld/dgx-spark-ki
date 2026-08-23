import time
import httpx
from typing import List, ClassVar
from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.rag_request.searchqdrant import SearchResult, SearchHit

class RerankHit(BaseModel):
    original_hit: SearchHit
    rerank_score: float
    rank: int

class RerankResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    query: str
    hits: List[RerankHit]
    duration_seconds: float

class RerankConfig(BaseModel):
    top_n: int = 5

@dataclass
class RerankRunContext(BaseRunContext[RerankConfig]):
    component_name: str
    config: RerankConfig

@component_registry.register('rerank')
class RerankBGE(BaseComponent):
    CONFIG_CLASS: ClassVar[type] = RerankConfig
    INPUT_CLASS: ClassVar[type] = SearchResult
    OUTPUT_CLASS: ClassVar[type] = RerankResult
    RUN_CONTEXT_CLASS: ClassVar[type] = RerankRunContext

    def run(self, data: SearchResult, *, component_ctx: RerankRunContext, global_ctx: GlobalRunContext) -> RerankResult:
        cfg = component_ctx.config
        start = time.time()

        with httpx.Client(base_url=global_ctx.infra.infinity_url, timeout=60.0) as client:
            resp = client.post("/rerank", json={
                "model": global_ctx.infra.MODEL_RERANKER,
                "query": data.query,
                "documents": [h.text for h in data.hits],
                "top_n": cfg.top_n,
                "return_documents": False
            })
            resp.raise_for_status()
            
            results = resp.json()["results"]
            reranked_hits = [RerankHit(
                original_hit=data.hits[item["index"]],
                rerank_score=item["relevance_score"],
                rank=rank
            ) for rank, item in enumerate(results, start=1)]

        return RerankResult(query=data.query, hits=reranked_hits, duration_seconds=round(time.time()-start, 3))
