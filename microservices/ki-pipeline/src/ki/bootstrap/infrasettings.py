from pydantic import computed_field
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class InfraSettings(BaseSettings):
    # 1. Infrastruktur (aus .env)
    HOST_PC: Optional[str] = None
    HOST_GPU: Optional[str] = None
    
    PORT_DOCLING: Optional[int] = None
    PORT_VLLM: Optional[int] = None
    PORT_INFINITY: Optional[int] = None
    PORT_QDRANT: Optional[int] = None
    
    MODEL_LLM: Optional[str] = None
    MODEL_LLM_small: Optional[str] = None
    MODEL_LLM_mycoder: Optional[str] = None
    MODEL_LLM_coder: Optional[str] = None

    MODEL_EMBEDDING: Optional[str] = None
    MODEL_RERANKER: Optional[str] = None
    
    HF_HOME: Optional[str] = None

    # 2. Secrets (aus .env.secret)
    HF_TOKEN: Optional[str] = None
    DB_PASSWORD: Optional[str] = None

    # 3. Berechnete URLs (Safe-Property Pattern)
    @computed_field
    @property
    def docling_url(self) -> Optional[str]:
        if self.HOST_GPU and self.PORT_DOCLING:
            return f"http://{self.HOST_GPU}:{self.PORT_DOCLING}"
        return None

    @computed_field
    @property
    def vllm_url(self) -> Optional[str]:
        if self.HOST_GPU and self.PORT_VLLM:
            return f"http://{self.HOST_GPU}:{self.PORT_VLLM}/v1"
        return None

    @computed_field
    @property
    def infinity_url(self) -> Optional[str]:
        if self.HOST_GPU and self.PORT_INFINITY:
            return f"http://{self.HOST_GPU}:{self.PORT_INFINITY}"
        return None

    @computed_field
    @property
    def qdrant_url(self) -> Optional[str]:
        if self.HOST_PC and self.PORT_QDRANT:
            return f"http://{self.HOST_PC}:{self.PORT_QDRANT}"
        return None

    # Konfiguration
    model_config = SettingsConfigDict(
        env_file=("/app/.env.infrastructure"),
        env_file_encoding='utf-8',
        extra="forbid",
        env_ignore_empty=False,
        env_nested_delimiter='--'
    )
