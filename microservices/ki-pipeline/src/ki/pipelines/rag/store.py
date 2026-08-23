import uuid
import time
from typing import List, ClassVar
from pydantic import BaseModel, Field
from dataclasses import dataclass

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.rag.embed import EmbedOutput

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, SparseVectorParams, SparseIndexParams, SparseVector

class IngestionResult(BaseComponentResult):
    source_path: str
    chunks_total: int
    chunks_stored: int
    parent_chunks_total: int = 0
    parent_chunks_stored: int = 0
    collection_name: str
    duration_seconds: float
    errors: List[str]

class StoreConfig(BaseModel):
    collection_name: str
    parent_collection_name: str = ""
    vector_size: int = 1024
    distance: str = "Cosine"
    use_sparse: bool = False

@dataclass
class StoreRunContext(BaseRunContext[StoreConfig]):
    component_name: str
    config: StoreConfig

@component_registry.register('store_qdrant')
class StoreQdrant(BaseComponent):
    CONFIG_CLASS: ClassVar[type] = StoreConfig
    INPUT_CLASS: ClassVar[type] = EmbedOutput
    OUTPUT_CLASS: ClassVar[type] = IngestionResult
    RUN_CONTEXT_CLASS: ClassVar[type] = StoreRunContext

    def _ensure_collections(self, client: QdrantClient, cfg: StoreConfig):
        parent_col = cfg.parent_collection_name or f"{cfg.collection_name}_parents"
        existing = [c.name for c in client.get_collections().collections]
        
        if cfg.collection_name not in existing:
            dist = Distance.COSINE if cfg.distance == "Cosine" else Distance.DOT
            client.create_collection(
                collection_name=cfg.collection_name,
                vectors_config={"dense": VectorParams(size=cfg.vector_size, distance=dist)},
                sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))} if cfg.use_sparse else None
            )
        
        if parent_col not in existing:
            client.create_collection(collection_name=parent_col, vectors_config={})

    def run(self, data: EmbedOutput, *, component_ctx: StoreRunContext, global_ctx: GlobalRunContext) -> IngestionResult:
        run_logger = global_ctx.run_logger
        cfg = component_ctx.config
        run_logger.info(f"Speichere Chunks in Qdrant ({global_ctx.infra.HOST_PC}:{global_ctx.infra.PORT_QDRANT})")
        client = QdrantClient(host=global_ctx.infra.HOST_PC, port=global_ctx.infra.PORT_QDRANT)
        start = time.time()
        errors = []
        
        parent_col = cfg.parent_collection_name or f"{cfg.collection_name}_parents"
        self._ensure_collections(client, cfg)

        # 1. Store Parents (Vektorleer)
        parent_stored = 0
        if data.parent_chunks:
            try:
                p_points = [PointStruct(id=p.id, vector={}, payload={"text": p.text, **p.meta}) for p in data.parent_chunks]
                client.upsert(collection_name=parent_col, points=p_points)
                parent_stored = len(p_points)
            except Exception as e: errors.append(f"Parent-Error: {e}")

        # 2. Store Children (Mit Vektoren und Preamble)
        child_points = []
        for ec in data.embedded_chunks:
            try:
                vecs = {"dense": ec.dense_vector}
                if cfg.use_sparse and ec.sparse_vector:
                    vecs["sparse"] = SparseVector(indices=list(ec.sparse_vector.keys()), values=list(ec.sparse_vector.values()))
                
                # Exakte Payload-Logik: parent_doc_id und context_preamble
                payload = {
                    "text": ec.chunk.text,
                    **ec.chunk.meta,
                    "parent_doc_id": ec.chunk.parent_id
                }
                if ec.context_preamble:
                    payload["context_preamble"] = ec.context_preamble

                child_points.append(PointStruct(id=str(uuid.uuid4()), vector=vecs, payload=payload))
            except Exception as e: errors.append(f"Point-Creation-Error: {e}")

        stored = 0
        if child_points:
            try:
                client.upsert(collection_name=cfg.collection_name, points=child_points)
                stored = len(child_points)
            except Exception as e: errors.append(f"Upsert-Error: {e}")

        return IngestionResult(
            source_path=str(data.source_path),
            chunks_total=len(data.embedded_chunks),
            chunks_stored=stored,
            parent_chunks_total=len(data.parent_chunks),
            parent_chunks_stored=parent_stored,
            collection_name=cfg.collection_name,
            duration_seconds=round(time.time() - start, 2),
            errors=errors
        )
