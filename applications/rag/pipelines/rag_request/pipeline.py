# applications/rag/pipelines/rag_request/pipeline.py

from typing import List, Type
from pydantic import BaseModel

from libs.pipeline.base import BasePipeline
from libs.pipeline.step import PipelineStep
from libs.pipeline.basemodels import BasePipelineEnv

from applications.rag.pipelines.rag_request.config import RagRequestConfig
from applications.rag.pipelines.rag_request.environment import RagRequestEnv
from applications.rag.pipelines.rag_request.steps.models import (
    QueryInput,
    EmbeddedQuery,
    SearchResult,
    RerankResult,
    EnrichedResult
)
from applications.rag.pipelines.rag_request.steps.embed import embed_action
from applications.rag.pipelines.rag_request.steps.search import search_action
from applications.rag.pipelines.rag_request.steps.rerank import rerank_action
from applications.rag.pipelines.rag_request.steps.fetch_parents import fetch_parents_action
from applications.rag.pipelines.rag_request.steps.generate import generate_action

class RagRequestPipeline(BasePipeline):
    """
    Kapselt das reine Manifest für die RAG Request Pipeline.
    """
    @property
    def pipeline_id(self) -> str:
        return "rag_request"

    @property
    def config_class(self) -> Type[BaseModel]:
        return RagRequestConfig

    @property
    def initial_input_class(self) -> Type[BaseModel]:
        return QueryInput

    def create_environment(self, config: RagRequestConfig) -> BasePipelineEnv:
        return RagRequestEnv(config=config.env)

    def build_steps(self, config: RagRequestConfig) -> List[PipelineStep]:
        step_cfgs = config.steps
        return [
            PipelineStep(
                name="EmbedQuery",
                input_class=QueryInput,
                config=step_cfgs.embed,
                step_action=embed_action
            ),
            PipelineStep(
                name="SearchQdrant",
                input_class=EmbeddedQuery,
                config=step_cfgs.search,
                step_action=search_action
            ),
            PipelineStep(
                name="RerankBGE",
                input_class=SearchResult,
                config=step_cfgs.rerank,
                step_action=rerank_action
            ),
            PipelineStep(
                name="FetchParents",
                input_class=RerankResult,
                config=step_cfgs.parent,
                step_action=fetch_parents_action        
            ),
            PipelineStep(
                name="GenerateLLM",
                input_class=EnrichedResult,
                config=step_cfgs.generate,
                step_action=generate_action
            )
        ]
