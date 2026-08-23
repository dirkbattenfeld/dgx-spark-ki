# libs/applications/rag/pipelines/rag_ingestion/config.py

from typing import Optional
from pydantic import BaseModel, Field
from libs.observability import ChannelConfig, ObservabilityConfig 

# Import der fachlichen Step-Configs
from applications.rag.pipelines.rag_ingestion.steps.configs import (
    ChunkConfig,
    ContextualizeConfig,
    EmbedConfig,
    ExtractConfig,
    StoreConfig
)
class IngestionEnvConfig(BaseModel):
    """Globale Infrastruktur- und Laufzeit-Einstellungen der Pipeline."""
    use_dispatcher: bool = True
    config_path: Optional[str] = None
    max_concurrent_documents: int = 5
    s3_bucket: str = "office-test"
    s3_glob_pattern: str = "*.pptx"   #"*.{pdf,docx,xlsx,pptx}"
    default_vllm_system_prompt: str = "Du bist ein präziser Dokumentanalyst."  

class PipelineStepConfigs(BaseModel):
    """Kapselt alle fachlichen Einstellungen für die einzelnen Steps."""
    extract: ExtractConfig = Field(
        default_factory=lambda: ExtractConfig(detailed_tables=True, ocr_enabled=True)
    )
    chunk: ChunkConfig = Field(
        default_factory=lambda: ChunkConfig(
            child_max_tokens=512, 
            max_child_chunks_per_parent=6, 
            parent_overlap_chunks=1, 
            merge_peers=True
        )
    )
    contextualize: ContextualizeConfig = Field(
        default_factory=lambda: ContextualizeConfig(
            max_tokens=256, 
            max_concurrent=32, 
            temperature=0.1, 
            document_window_chars=40000, 
            no_think=True
        )
    )
    embed: EmbedConfig = Field(
        default_factory=lambda: EmbedConfig(batch_size=64)
    )
    store: StoreConfig = Field(
        default_factory=lambda: StoreConfig(collection_name="test3", vector_size=1024, distance="Cosine")
    )


class RagIngestionConfig(BaseModel):
    """
    UNIFIED CONFIGURATION: Single Source of Truth für den Entwickler.
    Enthält sowohl Umgebungs- als auch Step-Konfigurationen.
    """
    env: IngestionEnvConfig = Field(default_factory=IngestionEnvConfig)
    steps: PipelineStepConfigs = Field(default_factory=PipelineStepConfigs)