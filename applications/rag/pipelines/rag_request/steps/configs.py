from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class EmbedQueryConfig(BaseModel):
    model_name: Optional[str] = "BAAI/bge-m3"  # Falls sparse genutzt wird
    extras: Dict[str, Any] = Field(default_factory=dict)

class SearchQdrantConfig(BaseModel):
    collection_name: str = "ba25-paper"
    limit: int = 20
    score_threshold: Optional[float] = None
    extras: Dict[str, Any] = Field(default_factory=dict)

class RerankConfig(BaseModel):
    top_n: int = 10
    extras: Dict[str, Any] = Field(default_factory=dict)

class ParentDocConfig(BaseModel):
    collection_name: str = "ba25-paper_parents"
    parent_id_field: str = "parent_doc_id"
    fetch_parent: bool = True
    extras: Dict[str, Any] = Field(default_factory=dict)

class GenerateConfig(BaseModel):
    generate: bool = True
    max_tokens: int = 8192
    temperature: float = 0.1
    no_think: bool = False
    max_context_chars: int = 100000
    system_prompt: str = "Du bist ein präziser Dokumentenassistent..."
    extras: Dict[str, Any] = Field(default_factory=dict)
    
class EmptyConfig(BaseModel):
        pass

