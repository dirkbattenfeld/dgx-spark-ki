import time
from typing import List, Dict, Any, ClassVar, Optional
from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.rag_request.embedquery import EmbeddedQuery

from qdrant_client import QdrantClient

class SearchHit(BaseModel):
    id: str
    score: float
    text: str
    context_preamble: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

class SearchResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    query: str
    hits: List[SearchHit]
    duration_seconds: float

class SearchConfig(BaseModel):
    collection_name: str = "iu"
    limit: int = 20  # Maximale Anzahl der Treffer 
    score_threshold: Optional[float] = None

@dataclass
class SearchRunContext(BaseRunContext[SearchConfig]):
    component_name: str
    config: SearchConfig

@component_registry.register('search_qdrant')
class SearchQdrant(BaseComponent):
    CONFIG_CLASS: ClassVar[type] = SearchConfig
    INPUT_CLASS: ClassVar[type] = EmbeddedQuery
    OUTPUT_CLASS: ClassVar[type] = SearchResult
    RUN_CONTEXT_CLASS: ClassVar[type] = SearchRunContext

    def run(self, data: EmbeddedQuery, *, component_ctx: SearchRunContext, global_ctx: GlobalRunContext) -> SearchResult:
        cfg = component_ctx.config
        
        client = QdrantClient(host=global_ctx.infra.HOST_PC, port=global_ctx.infra.PORT_QDRANT)
        start = time.time()

        raw_results = client.query_points(
            collection_name=cfg.collection_name,
            query=data.dense_vector,
            using="dense",
            limit=cfg.limit,
            score_threshold=cfg.score_threshold,
            with_payload=True,
        ).points

        hits = [SearchHit(
            id=str(p.id),
            score=p.score,
            text=p.payload.get("text", ""),
            context_preamble=p.payload.get("context_preamble"),
            meta={k: v for k, v in p.payload.items() if k not in ("text", "context_preamble")}
        ) for p in raw_results]

        return SearchResult(query=data.query, hits=hits, duration_seconds=round(time.time()-start, 3))