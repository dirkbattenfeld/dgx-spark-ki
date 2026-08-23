# applications/rag/pipelines/rag_request/api_bridge.py
from typing import List
from libs.streampipe.step import PipelineStep
from applications.rag.pipelines.rag_request.models import QueryInput, EmbeddedQuery, SearchResult, RerankResult, EnrichedResult

# Deine imports der Configs und Actions
from applications.rag.pipelines.rag_request.configs import (
    EmbedQueryConfig, SearchQdrantConfig, RerankConfig, ParentDocConfig, GenerateConfig
)
from applications.rag.pipelines.rag_request.steps.embed import embed_action
from applications.rag.pipelines.rag_request.steps.search import search_action
from applications.rag.pipelines.rag_request.steps.rerank import rerank_action
from applications.rag.pipelines.rag_request.steps.fetch_parents import fetch_parents_action
from applications.rag.pipelines.rag_request.steps.generate import generate_action


def create_rag_pipeline_steps() -> List[PipelineStep]:
    embed_config = EmbedQueryConfig()
    search_config = SearchQdrantConfig(collection_name="alanus-pptx", limit=10, score_threshold=0.7)
    rerank_config = RerankConfig(top_n=5)
    parent_config = ParentDocConfig(collection_name="alanus-pptx_parents", fetch_parent=True)
    generate_config = GenerateConfig(temperature=0.1, max_tokens=500, no_think=True, max_context_chars=100000)

    return [
        PipelineStep(name="EmbedQuery", input_class=QueryInput, config=embed_config, step_action=embed_action),
        PipelineStep(name="SearchQdrant", input_class=EmbeddedQuery, config=search_config, step_action=search_action),
        PipelineStep(name="RerankBGE", input_class=SearchResult, config=rerank_config, step_action=rerank_action),
        PipelineStep(name="FetchParents", input_class=RerankResult, config=parent_config, step_action=fetch_parents_action),
        PipelineStep(name="GenerateLLM", input_class=EnrichedResult, config=generate_config, step_action=generate_action)
    ]
