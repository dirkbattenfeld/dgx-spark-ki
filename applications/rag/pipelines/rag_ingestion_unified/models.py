from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from libs.streampipe.basemodels import BaseComponentResult

# --- STEP 1: Extract LOGIK ---
class ExtractInput(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: str
    extras: Dict[str, Any] = Field(default_factory=dict) 

class RawDocument(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: str
    markdown_content: str
    json_path: str 
    metadata: Dict[str, Any]
    status: str = "success"                             
    extras: Dict[str, Any] = Field(default_factory=dict)
    

# --- STEP 2: CHUNK LOGIK ---
class Chunk(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    text: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    parent_id: Optional[str] = None   
    
class ParentChunk(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    text: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    
class ChunkedDocument(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source: RawDocument
    chunks: List[Chunk]
    parent_chunks: List[ParentChunk] = Field(default_factory=list)
    status: str = "success"                             
    extras: Dict[str, Any] = Field(default_factory=dict)
   
    
# --- Step 4: Embeddings ----
class EmbeddedChunk(BaseModel):
    chunk: Any  # Nimmt das originale Chunk-Objekt auf
    dense_vector: List[float]
    context_preamble: Optional[str] = None


class EmbedOutput(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: str
    embedded_chunks: List[EmbeddedChunk]
    parent_chunks: List[Any]
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)


# --- Step 5: Store in Qdrant ---
class IngestionResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: str
    chunks_total: int
    chunks_stored: int
    parent_chunks_total: int = 0
    parent_chunks_stored: int = 0
    collection_name: str
    errors: List[str]
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)