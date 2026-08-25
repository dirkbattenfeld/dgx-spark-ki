from pydantic import BaseModel, Field
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional

@dataclass
class ChatTurn:
    """Represents a single conversation turn between user and bot."""
    user: str
    bot: str
    # Speichert die vollen Chunks dieses spezifischen Turns für die UI-Historie
    source_chunks: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class DomainSessionState:
    """Represents the complete state of a user's domain session including conversation history and basket."""
    history: List[ChatTurn]
    # Flache Liste der vom User aktivierten Qdrant-IDs (turnübergreifend)
    basket: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the domain session state to a dictionary representation."""
        return asdict(self)

    @classmethod
    def create_empty_initial(cls) -> "DomainSessionState":
        """Creates an empty initial domain session state."""
        return cls(history=[], basket=[])

    @classmethod
    def from_dict(cls, data: dict) -> "DomainSessionState":
        """Creates a domain session state from a dictionary representation."""
        return cls(
            history=[ChatTurn(**t) for t in data.get("history", [])],
            basket=data.get("basket", [])
        )

class RetrievalChunk(BaseModel):
    """Represents a retrieved chunk from the knowledge base with metadata and scoring information."""
    
    # IDs
    id: str = Field(..., description="ID des Child-Chunks (aus SearchHit)")
    parent_id: Optional[str] = Field(None, description="ID des Parent-Chunks (aus EnrichedHit)")
    
    # Texte
    text: str = Field(..., description="Text des Child-Chunks")
    parent_text: Optional[str] = Field(None, description="Volltext des Parent-Chunks")
    context_preamble: Optional[str] = Field(None, description="Optionale Einleitung/Metadaten-String")
    
    # Metadaten
    source_path: str = "Unbekannter Pfad"
    headings: str = ""
   
    # Scores & Ränge
    qdrant_score: float = 0.0
    qdrant_rank: int = 0
    rerank_score: float = 0.0
    rerank_rank: int = 0
    
    @classmethod
    def from_enriched_hit(cls, hit_dict: dict, fallback_index: int) -> "RetrievalChunk":
        """Factory-Methode, die ein EnrichedHit-Dict in ein DTO parst."""
        hit_dict = hit_dict or {}
        rerank_hit = hit_dict.get("rerank_hit") or {}
        original_hit = rerank_hit.get("original_hit") or {}
        meta = original_hit.get("meta") or {}
        
        headings_data = meta.get("headings") or []
        headings_str = ", ".join(headings_data) if isinstance(headings_data, list) else str(headings_data)

        return cls(
            id=original_hit.get("id") or f"chunk_{fallback_index}",
            parent_id=hit_dict.get("parent_id"),
            text=original_hit.get("text") or "",
            parent_text=hit_dict.get("parent_text") or "Kein Parent-Text verfügbar.",
            context_preamble=original_hit.get("context_preamble"),
            source_path=meta.get("source_path") or "Unbekannter Pfad",
            headings=headings_str,
            qdrant_score=float(original_hit.get("score") or 0.0),
            qdrant_rank=int(original_hit.get("rank") or (fallback_index + 1)),
            rerank_score=float(rerank_hit.get("rerank_score") or 0.0),
            rerank_rank=int(rerank_hit.get("rank") or (fallback_index + 1))
        )
        
class ChatSettings(BaseModel):
    """Configuration settings for chat interactions with the RAG system."""
    system_prompt: str
    collection_name: str = "alanus-pptx"
    collection_name_parents: str = "alanus-pptx_parents"
    limit: int = 100
    score_threshold: float = 0.5
    top_n: int = 5
    max_tokens: int = 1024
    temperature: float = 0.2
    generate: bool = True
    no_think: bool = True
    display_chunks: bool = False

class ParsedContext(BaseModel):
    """Represents the parsed and structured context of a user query after processing."""
    raw_query: str
    clean_query: str
    search_queries: List[str] = Field(default_factory=list)
    instructions: List[str] = Field(default_factory=list)
    active_template: Optional[str] = None
