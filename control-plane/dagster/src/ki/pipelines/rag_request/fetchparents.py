from typing import List, ClassVar, Optional
from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.rag_request.rerank import RerankResult, RerankHit

from qdrant_client import QdrantClient

class EnrichedHit(BaseModel):
    rerank_hit: RerankHit
    parent_text: Optional[str] = None
    parent_id: Optional[str] = None

class EnrichedResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    query: str
    hits: List[EnrichedHit]

class ParentDocConfig(BaseModel):
    collection_name: str = ""
    parent_id_field: str = "parent_doc_id"
    fetch_parent: bool = True

@dataclass
class ParentDocRunContext(BaseRunContext[ParentDocConfig]):
    component_name: str
    config: ParentDocConfig

@component_registry.register('fetch_parents')
class FetchParentDocs(BaseComponent):
    CONFIG_CLASS: ClassVar[type] = ParentDocConfig
    INPUT_CLASS: ClassVar[type] = RerankResult
    OUTPUT_CLASS: ClassVar[type] = EnrichedResult
    RUN_CONTEXT_CLASS: ClassVar[type] = ParentDocRunContext

    def run(self, data: RerankResult, *, component_ctx: ParentDocRunContext, global_ctx: GlobalRunContext) -> EnrichedResult:
        cfg = component_ctx.config
        enriched_hits = []
        client = QdrantClient(host=global_ctx.infra.HOST_PC, port=global_ctx.infra.PORT_QDRANT) if cfg.fetch_parent else None

        for rhit in data.hits:
            p_id = rhit.original_hit.meta.get(cfg.parent_id_field)
            p_text = None
            if cfg.fetch_parent and p_id and client:
                res = client.retrieve(collection_name=cfg.collection_name, ids=[p_id], with_payload=True)
                if res: p_text = res[0].payload.get("text")
            
            enriched_hits.append(EnrichedHit(rerank_hit=rhit, parent_text=p_text, parent_id=p_id))

        return EnrichedResult(query=data.query, hits=enriched_hits)
