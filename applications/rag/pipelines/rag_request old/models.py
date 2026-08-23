from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

# --- Input / Start der Pipeline ---
class QueryInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    prompt_query: str   # für Qdrant Suche
    prompt_llm: str     # prompt für LLM
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)

# --- Step 1: Embed ---
class EmbeddedQuery(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    prompt_query: str
    prompt_llm: str
    dense_vector: List[float]
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)

# --- Step 2: Search ---
class SearchHit(BaseModel):
    id: str
    score: float
    text: str
    context_preamble: Optional[str] = None
    rank: int
    meta: Dict[str, Any] = Field(default_factory=dict)
    
class SearchResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    prompt_query: str
    prompt_llm: str
    hits: List[SearchHit]
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)
    
# --- Step 3: Rerank ---
class RerankHit(BaseModel):
    original_hit: SearchHit
    rerank_score: float
    rank: int
    
class RerankResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    prompt_query: str
    prompt_llm: str
    hits: List[RerankHit]
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)
    
# --- Step 4: Fetch Parents ---
class EnrichedHit(BaseModel):
    rerank_hit: RerankHit
    parent_text: Optional[str] = None
    parent_id: Optional[str] = None

class EnrichedResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    prompt_query: str
    prompt_llm: str
    hits: List[EnrichedHit]
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)
    
# --- Step 5: Generate (Output) ---
class GenerationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    prompt_query: str
    prompt_llm: str
    answer: str
    prompt: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)
    
