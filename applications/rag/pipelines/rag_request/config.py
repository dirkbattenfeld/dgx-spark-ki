# libs/applications/rag/pipelines/rag_request/config.py

from typing import Optional
from pydantic import BaseModel, Field
from libs.observability import ChannelConfig, ObservabilityConfig 

# Import der fachlichen Step-Configs
from applications.rag.pipelines.rag_request.steps.configs import(
    EmbedQueryConfig,
    SearchQdrantConfig,
    RerankConfig,
    ParentDocConfig,
    GenerateConfig
)

class RequestEnvConfig(BaseModel):
    use_dispatcher: bool = True
    config_path: Optional[str] = None
    max_concurrency: int = 10
    
class PipelineStepConfigs(BaseModel):
    """Kapselt alle fachlichen Einstellungen für die einzelnen Steps."""
    
    embed: EmbedQueryConfig = Field(
        default_factory=lambda: EmbedQueryConfig()
    )
    search: SearchQdrantConfig = Field(
        default_factory=lambda: SearchQdrantConfig(
            collection_name="ki-paper",
            limit=10,
            score_threshold=0.5
        )
    )
    rerank: RerankConfig = Field(
        default_factory=lambda: RerankConfig(
            top_n=5
        )
    )
    parent: ParentDocConfig = Field(
        default_factory=lambda: ParentDocConfig(
            collection_name="ki-paper_parents",
            fetch_parent=True
        )
    )
    generate: GenerateConfig = Field(
        default_factory=lambda: GenerateConfig(
            temperature=0.1,
            max_tokens=500,
            no_think=True,
            max_context_chars=100000,
            system_prompt="Du bist ein präziser Dokumentenassistent..."
        )
    )

class RagRequestConfig(BaseModel):
    """
    UNIFIED CONFIGURATION: Single Source of Truth für den Entwickler.
    Enthält sowohl Umgebungs- als auch Step-Konfigurationen.
    """
    env: RequestEnvConfig = Field(default_factory=RequestEnvConfig)
    steps: PipelineStepConfigs = Field(default_factory=PipelineStepConfigs)
