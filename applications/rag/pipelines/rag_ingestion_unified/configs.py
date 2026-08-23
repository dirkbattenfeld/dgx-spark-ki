from typing import Any, Dict
from pydantic import BaseModel, Field

# --- STEP 1: EXTRACT LOGIK ---  
class ExtractConfig(BaseModel):
    detailed_tables: bool = True
    ocr_enabled: bool = True
    extras: Dict[str, Any] = Field(default_factory=dict) # nur für Fast Prototyping
    
# --- STEP 2: CHUNK LOGIK ---
class ChunkConfig(BaseModel):
    tokenizer_name: str = "BAAI/bge-m3"
    child_max_tokens: int = 512
    max_child_chunks_per_parent: int = 3
    parent_overlap_chunks: int = 0
    merge_peers: bool = True
    extras: Dict[str, Any] = Field(default_factory=dict)

# --- Step 3: Contextualize ---
class ContextualizeConfig(BaseModel):
    max_tokens: int = 256
    temperature: float = 0.0
    document_window_chars: int = 6000     # Chunks werden im Kontext des LLM auf diese Länge abgeschnitten
    max_concurrent: int = 16
    no_think: bool = True
    extras: Dict[str, Any] = Field(default_factory=dict)
    
# --- Step 4: Embeddings ---
class EmbedConfig(BaseModel):
    batch_size: int = 32
    model: str = "BAAI/bge-m3"
    extras: Dict[str, Any] = Field(default_factory=dict)
    

# --- Step 5: Store in Qdrant ---
class StoreConfig(BaseModel):
    collection_name: str
    parent_collection_name: str = ""
    vector_size: int = 1024
    distance: str = "Cosine"
    extras: Dict[str, Any] = Field(default_factory=dict)
    