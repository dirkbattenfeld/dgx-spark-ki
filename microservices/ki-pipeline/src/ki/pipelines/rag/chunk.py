import logging
import httpx
import uuid
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.rag.extract import RawDocument

# --- Datenmodelle ---
class Chunk(BaseModel):
    text: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    parent_id: Optional[str] = None   
    
class ParentChunk(BaseModel):
    id: str
    text: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    
class ChunkedDocument(BaseComponentResult):
    source: RawDocument
    chunks: List[Chunk]
    parent_chunks: List[ParentChunk] = Field(default_factory=list)

class ChunkConfig(BaseModel):
    timeout: float = 300.0
    
    # Chunking Parameter (werden an API durchgereicht)
    child_max_tokens: int = 512
    merge_peers: bool = True
    
    # Lokale Logik Parameter (Orchestrator)
    children_per_parent: int = 5         
    parent_overlap: int = 1   

@dataclass
class ChunkDoclingRunContext(BaseRunContext[ChunkConfig]):
    component_name: str
    config: ChunkConfig
   
    def __post_init__(self):
        super().__init__(component_name=self.component_name, config=self.config)

# --- Komponente ---

@component_registry.register('chunk_docling')
class ChunkDocling(BaseComponent):
    CONFIG_CLASS = ChunkConfig
    INPUT_CLASS = RawDocument
    OUTPUT_CLASS = ChunkedDocument
    RUN_CONTEXT_CLASS = ChunkDoclingRunContext

    def _build_parent_child_pairs(
        self, child_chunks: List[Chunk], config: ChunkConfig
    ) -> tuple[List[ParentChunk], List[Chunk]]:
        """
        Reine Python-Logik: Gruppiert Child-Chunks zu überlappenden Parent-Chunks.
        Läuft lokal im Orchestrator ohne Docling-Abhängigkeit.
        """
        step = max(1, config.children_per_parent - config.parent_overlap)
        parent_chunks: List[ParentChunk] = []
        assigned_indices: set[int] = set()

        # Arbeitskopien initialisieren
        enriched: List[Chunk] = [
            Chunk(text=c.text, meta=c.meta, parent_id=None) for c in child_chunks
        ]

        for i in range(0, len(child_chunks), step):
            group = list(range(i, min(i + config.children_per_parent, len(child_chunks))))
            if not group:
                continue

            parent_id = str(uuid.uuid4())
            parent_text = " ".join(child_chunks[j].text for j in group)

            # Metadaten: Seitenspanne des gesamten Parents aggregieren
            all_pages = []
            for j in group:
                all_pages.extend(child_chunks[j].meta.get("page_numbers", []))
            
            parent_meta = {
                "source": child_chunks[group[0]].meta.get("source", ""),
                "headings": child_chunks[group[0]].meta.get("headings", []),
                "page_numbers": sorted(set(all_pages)),
            }

            parent_chunks.append(ParentChunk(id=parent_id, text=parent_text, meta=parent_meta))

            # Child-IDs eindeutig zuweisen (erster Parent gewinnt)
            for j in group:
                if j not in assigned_indices:
                    assigned_indices.add(j)
                    enriched[j].parent_id = parent_id

        return parent_chunks, enriched

    def run(self, data: RawDocument, *, component_ctx: ChunkDoclingRunContext, global_ctx: GlobalRunContext) -> ChunkedDocument:
        run_logger = global_ctx.run_logger
        cfg = component_ctx.config
        
        run_logger.info(f"Starte Chunking-Prozess für {data.source_path} mit Docling-Service unter {global_ctx.infra.docling_url}.")

        # 1. API Call an den Docling Service (Der schwere ML-Teil)
        try:
            with httpx.Client(base_url=global_ctx.infra.docling_url, timeout=cfg.timeout) as client:
                payload = {
                    "json_path": str(data.json_path),
                    "source_path": str(data.source_path),
                    "config": {
                        "tokenizer_name": global_ctx.infra.MODEL_EMBEDDING,
                        "child_max_tokens": cfg.child_max_tokens,
                        "merge_peers": cfg.merge_peers
                    }
                }
                
                response = client.post("/chunk", json=payload)
                response.raise_for_status()
                result_data = response.json()
                
                raw_chunks = result_data.get("chunks", [])
                run_logger.info(f"Service lieferte {len(raw_chunks)} Basis-Chunks zurück.")

                # Mapping der API-Antwort auf lokale Chunk-Modelle
                child_chunks = [
                    Chunk(text=c["text"], meta=c["meta"]) for c in raw_chunks
                ]

        except Exception as e:
            run_logger.error(f"Fehler beim Aufruf des Chunking-Services: {str(e)}")
            raise

        # 2. Lokale Logik (UUIDs und Parent-Fenster bauen)
        run_logger.info("Erstelle Parent-Child Beziehungen.")
        parent_chunks, enriched_children = self._build_parent_child_pairs(child_chunks, cfg)

        run_logger.info(
            f"Chunking beendet: {len(enriched_children)} Chunks, "
            f"{len(parent_chunks)} Parent-Fenster erzeugt."
        )

        return ChunkedDocument(
            source=data,
            chunks=enriched_children,
            parent_chunks=parent_chunks
        )
