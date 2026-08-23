import os
import sys
import json
import numpy as np
from pathlib import Path
from docling.document_converter import DocumentConverter
from typing import Any, List, Dict, Optional, ClassVar
from pydantic import BaseModel, Field
from docling_core.types.doc import DoclingDocument
from docling.chunking import HybridChunker
from transformers import AutoTokenizer
from huggingface_hub import login
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    SparseVector, SparseVectorParams, SparseIndexParams,
    NamedVector, NamedSparseVector
)
import uuid
import time

token = os.getenv("HF_TOKEN")
if token:
    login(token=token)

class Extract_Input(BaseModel):
    source_pdf: str
    page_range: bool = False
    first_page: int
    last_page: int

class RawDocument(BaseModel):
    source_path: str
    content: DoclingDocument      # nativer Docling-Typ
    markdown_content: str
    metadata: Any
    
    class Config:
        arbitrary_types_allowed = True

class Chunk(BaseModel):
    text: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    parent_id: Optional[str] = None   
    
class ParentChunk(BaseModel):
    id: str
    text: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    
class ChunkedDocument(BaseModel):
    source: RawDocument
    chunks: List[Chunk]           # text + bbox + page + hierarchy
    parent_chunks: List[ParentChunk] = Field(default_factory=list)

class EmbeddedChunk(BaseModel):
    chunk: Chunk
    dense_vector: List[float]
    sparse_vector: Dict[int, float]   # für BGE-M3 hybrid
    context_preamble: Optional[str] = None      # Contextualize-Schritt

class IngestionResult(BaseModel):
    source_path: str
    chunks_total: int
    chunks_stored: int
    parent_chunks_total: int = 0         
    parent_chunks_stored: int = 0        
    collection_name: str
    duration_seconds: float
    errors: List[str]

class Extract_Config(BaseModel):
    pass

class ChunkConfig(BaseModel):
    tokenizer_name: str = "BAAI/bge-m3"
    child_max_tokens: int = 512        # BGE-M3 Optimum: 512, Maximum: 8192
    merge_peers: bool = True     # benachbarte kleine Chunks zusammenführen
    children_per_parent: int = 5         
    parent_overlap: int = 1   

class GlobalRunContext(BaseModel):
    output_path: str = "/app/output"
    save_markdown: bool = False
    save_chunks: bool = False
    save_parent_chunks: bool = False     
    save_embeddings: bool = False
    save_ingestion_result: bool = False


# Funktionen zum Persistieren von (Zwischen-)ergebnissen
def _output_dir(global_ctx: GlobalRunContext) -> Path:
    d = Path(global_ctx.output_path)
    d.mkdir(parents=True, exist_ok=True)
    return d

def _stem(source_path: str, first_page: int, last_page: int) -> str:
    return f"{Path(source_path).stem}_p{first_page}-p{last_page}"


def save_markdown(
    extract_input: Extract_Input,
    extracted_document: RawDocument,
    global_ctx: GlobalRunContext,
):
    if not global_ctx.save_markdown:
        return
    if extract_input.page_range:
        stem = _stem(extract_input.source_pdf, extract_input.first_page, extract_input.last_page)
    else:
        stem = f"{Path(extract_input.source_pdf).stem}"
        
    target = _output_dir(global_ctx) / f"{stem}.md"
    target.write_text(extracted_document.markdown_content, encoding="utf-8")
    print(f"[persist] Markdown → {target}")


def save_chunks(
    extract_input: Extract_Input,
    chunked_document: ChunkedDocument,
    global_ctx: GlobalRunContext,
):
    """
    Speichert alle Chunks als JSONL – ein Chunk pro Zeile.
    Jede Zeile enthält Index, Text und Metadaten.
    Ideal um zu prüfen ob Tabellen intakt geblieben sind.
    """
    if not global_ctx.save_chunks:
        return
    stem = _stem(extract_input.source_pdf, extract_input.first_page, extract_input.last_page)
    target = _output_dir(global_ctx) / f"{stem}_chunks.jsonl"
    with target.open("w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunked_document.chunks):
            record = {"index": i, "text": chunk.text, "meta": chunk.meta}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"[persist] {len(chunked_document.chunks)} Chunks → {target}")
    

def save_parent_chunks(
    extract_input: Extract_Input,
    chunked_document: ChunkedDocument,
    global_ctx: GlobalRunContext,
):
    if not global_ctx.save_parent_chunks:
        return
    stem = _stem(extract_input.source_pdf, extract_input.first_page, extract_input.last_page)
    target = _output_dir(global_ctx) / f"{stem}_parent_chunks.jsonl"
    with target.open("w", encoding="utf-8") as f:
        for i, pc in enumerate(chunked_document.parent_chunks):
            record = {"index": i, "id": pc.id, "text": pc.text, "meta": pc.meta}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"[persist] {len(chunked_document.parent_chunks)} Parent-Chunks → {target}")


def save_ingestion_result(
    extract_input: Extract_Input,
    result: IngestionResult,
    global_ctx: GlobalRunContext,
):
    if not global_ctx.save_ingestion_result:
        return
    stem = _stem(extract_input.source_pdf, extract_input.first_page, extract_input.last_page)
    target = _output_dir(global_ctx) / f"{stem}_ingestion_result.json"
    target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"[persist] IngestionResult → {target}")


# Klassen der Ingestion-Pipeline
class Extract_Docling:
    CONFIG_CLASS: ClassVar[type] = Extract_Config
    INPUT_CLASS: ClassVar[type] = Extract_Input
    OUTPUT_CLASS: ClassVar[type] = RawDocument
 
    def __init__(self, config: Extract_Config):
        self.config = config
            
    def run(self, data: Extract_Input):
        source_pdf = data.source_pdf
        if data.page_range:
            print(f"Konvertiere {source_pdf} (Seiten {data.first_page} bis {data.last_page})...")   
            converter = DocumentConverter()
            result = converter.convert(source_pdf, page_range=(data.first_page, data.last_page))
        else:
            print(f"Konvertiere {source_pdf} ...")   
            converter = DocumentConverter()
            result = converter.convert(source_pdf)
            
        markdown_content = result.document.export_to_markdown()
        output = RawDocument(
            source_path = source_pdf, 
            content = result.document,
            markdown_content = markdown_content,
            metadata = {}
        )
        return output 


class Chunk_Docling:
    """
    Intelligentes Parent/Child-Chunking über Doclings HybridChunker.

    Child-Chunks (embedded, für Retrieval):
    - max_tokens=child_max_tokens (default 128)
    - respektieren Dokumentstruktur, Tabellen bleiben intact

    Parent-Chunks (nicht embedded, für LLM-Kontext):
    - Gruppierung von children_per_parent Child-Chunks
    - überlappende Parent-Fenster via parent_overlap
    - jeder Child-Chunk trägt parent_id seines ersten Parents

    Nur Child-Chunks werden kontextualisiert und embedded —
    Parent-Chunks werden direkt als LLM-Kontext genutzt.
    """
    CONFIG_CLASS: ClassVar[type] = ChunkConfig
    INPUT_CLASS: ClassVar[type] = RawDocument
    OUTPUT_CLASS: ClassVar[type] = ChunkedDocument

    def __init__(self, config: ChunkConfig):
        self.config = config
        print(f"Lade Tokenizer {config.tokenizer_name} für Chunk-Größenmessung...")
        tokenizer = AutoTokenizer.from_pretrained(config.tokenizer_name)
        self.chunker = HybridChunker(
            tokenizer=tokenizer,
            max_tokens=config.child_max_tokens,  
            merge_peers=config.merge_peers,
        )

    def _extract_chunk_meta(self, dl_chunk, source_path: str) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        headings = []
        if hasattr(dl_chunk, "meta") and dl_chunk.meta is not None:
            if hasattr(dl_chunk.meta, "headings") and dl_chunk.meta.headings:
                headings = list(dl_chunk.meta.headings)
        meta["headings"] = headings

        page_numbers: List[int] = []
        if hasattr(dl_chunk, "meta") and dl_chunk.meta is not None:
            if hasattr(dl_chunk.meta, "doc_items"):
                for item in dl_chunk.meta.doc_items:
                    if hasattr(item, "prov"):
                        for prov in item.prov:
                            if hasattr(prov, "page_no"):
                                page_numbers.append(prov.page_no)
        meta["page_numbers"] = sorted(set(page_numbers))

        if hasattr(dl_chunk, "meta") and dl_chunk.meta is not None:
            if hasattr(dl_chunk.meta, "doc_items"):
                meta["doc_items_count"] = len(dl_chunk.meta.doc_items)

        meta["source"] = source_path
        return meta

    def _build_parent_child_pairs(
        self, child_chunks: List[Chunk]
    ) -> tuple[List[ParentChunk], List[Chunk]]:
        """
        Gruppiert Child-Chunks zu überlappenden Parent-Chunks.

        Parent-Texte überlappen (parent_overlap) für lückenlosen Kontext.
        Jeder Child-Chunk wird genau einmal embedded — er bekommt die
        parent_id des ersten Parents dem er zugewiesen wurde.
        Overlap existiert nur auf Parent-Text-Ebene, nicht auf Child-ID-Ebene.
        """
        step = max(1, self.config.children_per_parent - self.config.parent_overlap)
        parent_chunks: List[ParentChunk] = []
        assigned_indices: set[int] = set()

        # Arbeitskopien mit leerem parent_id
        enriched: List[Chunk] = [
            Chunk(text=c.text, meta=c.meta, parent_id=None) for c in child_chunks
        ]

        for i in range(0, len(child_chunks), step):
            group = list(range(i, min(i + self.config.children_per_parent, len(child_chunks))))
            if not group:
                continue

            parent_id = str(uuid.uuid4())
            parent_text = " ".join(child_chunks[j].text for j in group)

            # Metadaten: Seitenspanne des gesamten Parents
            all_pages = []
            for j in group:
                all_pages.extend(child_chunks[j].meta.get("page_numbers", []))
            parent_meta = {
                "source": child_chunks[group[0]].meta.get("source", ""),
                "headings": child_chunks[group[0]].meta.get("headings", []),
                "page_numbers": sorted(set(all_pages)),
            }

            parent_chunks.append(ParentChunk(id=parent_id, text=parent_text, meta=parent_meta))

            # Child-IDs eindeutig zuweisen — jeder Index nur beim ersten Parent
            for j in group:
                if j not in assigned_indices:
                    assigned_indices.add(j)
                    enriched[j] = Chunk(
                        text=child_chunks[j].text,
                        meta=child_chunks[j].meta,
                        parent_id=parent_id,
                    )

        return parent_chunks, enriched

    def run(self, data: RawDocument) -> ChunkedDocument:
        print("Starte intelligentes Parent/Child-Chunking...")
        dl_chunks = list(self.chunker.chunk(dl_doc=data.content))
        print(f"HybridChunker erzeugte {len(dl_chunks)} Rohchunks (Child-Ebene).")

        child_chunks: List[Chunk] = []
        for dl_chunk in dl_chunks:
            text = self.chunker.serialize(chunk=dl_chunk)
            if not text.strip():
                continue
            meta = self._extract_chunk_meta(dl_chunk, data.source_path)
            child_chunks.append(Chunk(text=text, meta=meta))

        print(f"Child-Chunks: {len(child_chunks)} verwertbare Chunks.")

        parent_chunks, enriched_children = self._build_parent_child_pairs(child_chunks)
        print(
            f"Parent-Chunks: {len(parent_chunks)} erzeugt "
            f"(je {self.config.children_per_parent} Children, "
            f"overlap={self.config.parent_overlap})."
        )

        return ChunkedDocument(
            source=data,
            chunks=enriched_children,       # Child-Chunks mit parent_id → werden embedded
            parent_chunks=parent_chunks,    # Parent-Chunks ohne Vektoren → für LLM
        )
            

import asyncio
import time
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import ClassVar, List, Dict, Any, Optional


# ── Config ─────────────────────────────────────────────────────────────────────

class ContextualizeConfig(BaseModel):
    base_url: str = "http://gx10:8888/v1"
    api_key: str = "no-key"           # vLLM braucht irgendeinen Wert
    model: str = "Qwen/Qwen2.5-Coder-3B-Instruct"           # Qwen/Qwen3-8B / Qwen/Qwen2.5-Coder-3B-Instruct / nvidia/Qwen3-Next-80B-A3B-Instruct-NVFP4
    max_tokens: int = 256             # Preamble ist kurz
    temperature: float = 0.0          # deterministisch
    # Wieviel Zeichen des Gesamtdokuments als Kontext mitgeben
    # Zu groß = Prompt explodiert, zu klein = kein Mehrwert
    document_window_chars: int = 6000
    # Parallelität: wie viele Chunks gleichzeitig an vLLM schicken
    max_concurrent: int = 8
    # /no_think erzwingt direkten Output ohne CoT bei Qwen3
    no_think: bool = True


# ── Persistierung ──────────────────────────────────────────────────────────────

def save_contextualized_chunks(
    extract_input: "Extract_Input",
    chunked_document: "ChunkedDocument",
    global_ctx: "GlobalRunContext",
):
    """
    Speichert Chunks nach Contextualization als JSONL.
    Zeigt text + context_preamble nebeneinander – ideal um zu prüfen
    ob der Kontext inhaltlich zum Chunk passt.
    """
    if not global_ctx.save_chunks:
        return
    stem = _stem(extract_input.source_pdf, extract_input.first_page, extract_input.last_page)
    target = _output_dir(global_ctx) / f"{stem}_chunks_contextualized.jsonl"
    with target.open("w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunked_document.chunks):
            record = {
                "index": i,
                "context_preamble": chunk.meta.get("context_preamble", ""),
                "text": chunk.text,
                "headings": chunk.meta.get("headings", []),
                "page_numbers": chunk.meta.get("page_numbers", []),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"[persist] Contextualized Chunks → {target}")


class Contextualize_Qwen:
    """
    Reichert jeden Chunk mit einem kurzen Kontext-Preamble an,
    das den Chunk im Gesamtdokument verortet.

    Basiert auf dem Anthropic Contextual Retrieval Paper:
    Für jeden Chunk wird dem LLM das Gesamtdokument (oder ein Fenster davon)
    und der Chunk gezeigt. Das LLM schreibt 1-2 Sätze die erklären
    *wo im Dokument* dieser Chunk steht und *was sein Zweck* ist.

    Das Preamble wird in chunk.meta["context_preamble"] gespeichert.
    Embed_BGE nutzt es dann als Präfix beim Embedding:
        embed(preamble + "\\n" + chunk.text)

    Parallelität über asyncio + Semaphore um vLLM nicht zu überlasten.
    """
    CONFIG_CLASS: ClassVar[type] = ContextualizeConfig
    INPUT_CLASS: ClassVar[type] = "ChunkedDocument"
    OUTPUT_CLASS: ClassVar[type] = "ChunkedDocument"

    SYSTEM_PROMPT = (
        "Du bist ein präziser Dokumentanalyst. "
        "Deine Aufgabe ist es, einen kurzen Kontext für einen Textabschnitt zu formulieren, "
        "der erklärt wo im Dokument dieser Abschnitt steht und welche Rolle er spielt. "
        "Antworte ausschließlich mit dem Kontext, ohne Einleitung oder Erklärung. "
        "Maximal 2 Sätze."
    )

    def __init__(self, config: ContextualizeConfig):
        self.config = config
        self.client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )

    def _build_prompt(self, document_window: str, chunk: "Chunk") -> str:
        headings = " > ".join(chunk.meta.get("headings", []))
        pages = chunk.meta.get("page_numbers", [])
        location_hint = ""
        if headings:
            location_hint += f"Abschnittsebene: {headings}\n"
        if pages:
            location_hint += f"Seite(n): {', '.join(str(p) for p in pages)}\n"

        # /no_think am Ende des User-Prompts unterdrückt Qwen3 CoT
        no_think_suffix = " /no_think" if self.config.no_think else ""

        return (
            f"Hier ist ein Auszug aus dem Dokument als Kontext:\n"
            f"<document>\n{document_window}\n</document>\n\n"
            f"{location_hint}"
            f"Hier ist der Chunk:\n"
            f"<chunk>\n{chunk.text}\n</chunk>\n\n"
            f"Formuliere einen kurzen Kontext (1-2 Sätze) der erklärt, "
            f"wo im Dokument dieser Chunk steht und welchem Zweck er dient.{no_think_suffix}"
        )

    def _call_vllm(self, prompt: str) -> str:
        """Synchroner Call gegen vLLM OpenAI-Endpoint."""
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[warn] vLLM Call fehlgeschlagen: {e}")
            return ""

    def _document_window(self, full_markdown: str) -> str:
        """
        Gibt die ersten document_window_chars Zeichen des Dokuments zurück.
        Bei sehr langen Dokumenten ist das ausreichend um Struktur und
        Thema zu erfassen – für spätere Kapitel müsste man ein
        gleitendes Fenster implementieren.
        """
        return full_markdown[: self.config.document_window_chars]

    def run(self, data: "ChunkedDocument") -> "ChunkedDocument":
        start = time.time()
        document_window = self._document_window(data.source.markdown_content)
        chunks = data.chunks
        total = len(chunks)
        print(f"Starte Contextualization für {total} Chunks "
              f"(concurrency={self.config.max_concurrent})...")

        # Async Ausführung mit Semaphore für Parallelitätskontrolle
        async def process_all() -> List[str]:
            sem = asyncio.Semaphore(self.config.max_concurrent)
            loop = asyncio.get_event_loop()

            async def process_one(chunk: "Chunk", idx: int) -> str:
                async with sem:
                    prompt = self._build_prompt(document_window, chunk)
                    # vLLM-Call ist synchron → in Executor auslagern
                    preamble = await loop.run_in_executor(
                        None, self._call_vllm, prompt
                    )
                    if idx % 10 == 0:
                        print(f"  [{idx+1}/{total}] ✓")
                    return preamble

            return await asyncio.gather(
                *[process_one(chunk, i) for i, chunk in enumerate(chunks)]
            )

        preambles = asyncio.run(process_all())

        # Preamble in chunk.meta schreiben
        enriched_chunks: List[Chunk] = []
        for chunk, preamble in zip(chunks, preambles):
            new_meta = {**chunk.meta, "context_preamble": preamble}
            enriched_chunks.append(Chunk(text=chunk.text, meta=new_meta))

        elapsed = round(time.time() - start, 1)
        print(f"Contextualization abgeschlossen: {total} Chunks in {elapsed}s "
              f"({elapsed/total:.1f}s/Chunk)")

        return ChunkedDocument(
            source=data.source,
            chunks=enriched_chunks,
            parent_chunks=data.parent_chunks
        )


# --------------------------- Embeddings erzeugen ------------------------------

class EmbedConfig(BaseModel):
    model_name: str = "BAAI/bge-m3"
    # Infinity Endpunkt Konfiguration
    api_base: str = "http://gx10:7997"
    batch_size: int = 32
    # Diese Felder bleiben für die Kompatibilität,
    # die Steuerung erfolgt aber nun primär über den Infinity-Service
    normalize: bool = True
    return_sparse: bool = False   # Aktivieren sobald Sparse verfügbar / infinity liefert zurzeit nur dense
    

def save_embeddings(
    extract_input: Extract_Input,
    embedded_chunks: List[EmbeddedChunk],
    global_ctx: GlobalRunContext,
):
    """
    Speichert Embeddings als zwei Dateien:
    - _embeddings_meta.jsonl  → Text + sparse_vector + context_preamble (lesbar)
    - _embeddings_dense.npy   → dense Vektoren als numpy Array (kompakt)
    Damit kannst du mit np.load() + jsonl die Pipeline ohne Qdrant nachvollziehen.
    """
    if not global_ctx.save_embeddings:
        return
    stem = _stem(extract_input.source_pdf, extract_input.first_page, extract_input.last_page)
    out = _output_dir(global_ctx)

    # Lesbare Metadaten
    meta_target = out / f"{stem}_embeddings_meta.jsonl"
    with meta_target.open("w", encoding="utf-8") as f:
        for i, ec in enumerate(embedded_chunks):
            record = {
                "index": i,
                "text": ec.chunk.text,
                "meta": ec.chunk.meta,
                "sparse_vector_nnz": len(ec.sparse_vector),   # Anzahl non-zero Einträge
                "sparse_vector": {str(k): v for k, v in ec.sparse_vector.items()},
                "context_preamble": ec.context_preamble,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    # Dense Vektoren kompakt
    dense_target = out / f"{stem}_embeddings_dense.npy"
    matrix = np.array([ec.dense_vector for ec in embedded_chunks], dtype=np.float32)
    np.save(str(dense_target), matrix)

    print(f"[persist] {len(embedded_chunks)} Embeddings → {meta_target}, {dense_target}")



import requests

class Embed_BGE:
    """
    Erwartet einen ChunkedDocument, gibt List[EmbeddedChunk] zurück.
    Nutzt den Infinity Microservice für Dense + Sparse Vektoren.
    """
    CONFIG_CLASS: ClassVar[type] = EmbedConfig
    INPUT_CLASS: ClassVar[type] = Any # In deinem Code 'ChunkedDocument'
    OUTPUT_CLASS: ClassVar[type] = List[EmbeddedChunk]

    def __init__(self, config: EmbedConfig):
        self.config = config
        print(f"[Remote] Nutze Infinity-Service für {config.model_name} unter {config.api_base}")

    def run(self, data: Any) -> List[EmbeddedChunk]:
        texts = []
        for chunk in data.chunks:
            preamble = chunk.meta.get("context_preamble", "")
            if preamble:
                texts.append(f"{preamble}\n\n{chunk.text}")
            else:
                texts.append(chunk.text)

        print(f"Sende {len(texts)} Chunks an Infinity (Remote)...")

        # 1. Abfrage der DENSE Vektoren
        dense_response = requests.post(
            f"{self.config.api_base}/embeddings",
            json={
                "model": self.config.model_name,
                "input": texts
            }
        )
        dense_response.raise_for_status()
        dense_data = dense_response.json()["data"]       
        print(f"DEBUG Dense: Typ={type(dense_data[0]['embedding'])}, Dimension={len(dense_data[0]['embedding'])}")

        # 2. Abfrage der SPARSE Vektoren (optional, falls konfiguriert)
        sparse_data = None
        if self.config.return_sparse:
            try:
                sparse_response = requests.post(
                    f"{self.config.api_base}/embeddings", # <--- Gleicher Endpunkt wie Dense
                    json={
                        "model": self.config.model_name, 
                        "input": texts,
                        "embedding_type": "sparse"       # <--- Hinzufügen für V2 Sparse-Modus
                    },
                    timeout=10
                )
                sparse_response.raise_for_status()
                sparse_data = sparse_response.json()["data"]
            except requests.exceptions.HTTPError as e:
                print(f"⚠️ Sparse-Endpunkt nicht verfügbar (404). Fahre nur mit Dense fort. Fehler: {e}")
                sparse_data = None

        embedded_chunks = []
        for i, chunk in enumerate(data.chunks):
            # Extraktion Dense
            dense_vector = dense_data[i]["embedding"]

            # Extraktion Sparse (Konvertierung der Keys zu int für BGE-M3 Kompatibilität)
            sparse_vector: Dict[int, float] = {}
            if sparse_data:
                raw_sparse = sparse_data[i]["embedding"]
                sparse_vector = {int(k): float(v) for k, v in raw_sparse.items()}

                # Debug-Print nur beim allerersten Chunk des Batches
                if i == 0:
                    sample_key = list(sparse_vector.keys())[0] if sparse_vector else "N/A"
                    print(f"DEBUG Sparse: {len(sparse_vector)} Keys gefunden. Sample Key: {sample_key}")
                    
            embedded_chunks.append(EmbeddedChunk(
                chunk=chunk,
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                context_preamble=chunk.meta.get("context_preamble")
            ))

        print(f"Remote Embedding abgeschlossen: {len(embedded_chunks)} Chunks.")
        return embedded_chunks


# ---------------------------- Speichern in Qdrant -------------------------

class StoreConfig(BaseModel):
    host: str = "ryzon9"
    port: int = 6333
    collection_name: str
    parent_collection_name: str = "" 
    vector_size: int = 1024
    distance: str = "Cosine"    
    use_sparse: bool = False     # Umstellen sobald Sparse verfügbar ist


class Store_Qdrant:
    """
    Speichert Child-Chunks (mit Vektoren) und Parent-Chunks (ohne Vektoren)
    in zwei separate Qdrant-Collections.

    Child-Collection: collection_name — für Hybrid-Suche
    Parent-Collection: collection_name_parents — nur Payload-Lookup per ID
    """
    CONFIG_CLASS: ClassVar[type] = StoreConfig
    INPUT_CLASS: ClassVar[type] = List[EmbeddedChunk]
    OUTPUT_CLASS: ClassVar[type] = IngestionResult

    def __init__(self, config: StoreConfig):
        self.config = config
        self.client = QdrantClient(host=config.host, port=config.port)
        # ← NEU: Parent-Collection-Name ableiten
        self._parent_collection = (
            config.parent_collection_name
            if config.parent_collection_name
            else f"{config.collection_name}_parents"
        )
        self._ensure_collection()
        self._ensure_parent_collection()     # ← NEU

    def _ensure_collection(self):
        # unverändert
        existing = [c.name for c in self.client.get_collections().collections]
        if self.config.collection_name in existing:
            print(f"Collection '{self.config.collection_name}' existiert bereits.")
            return

        print(f"Erstelle Collection '{self.config.collection_name}'...")
        distance = Distance.COSINE if self.config.distance == "Cosine" else Distance.DOT
        vectors_config = {
            "dense": VectorParams(size=self.config.vector_size, distance=distance)
        }
        sparse_config = None
        if self.config.use_sparse:
            sparse_config = {
                "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
            }
            print("-> Sparse-Unterstützung aktiviert.")

        self.client.create_collection(
            collection_name=self.config.collection_name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_config,
        )
        print("Collection erfolgreich erstellt.")

    # ← NEU
    def _ensure_parent_collection(self):
        """Parent-Collection ohne Vektor-Index — nur Payload-Lookup."""
        existing = [c.name for c in self.client.get_collections().collections]
        if self._parent_collection in existing:
            print(f"Parent-Collection '{self._parent_collection}' existiert bereits.")
            return
        print(f"Erstelle Parent-Collection '{self._parent_collection}'...")
        self.client.create_collection(
            collection_name=self._parent_collection,
            vectors_config={},  # kein Vektor-Index
        )
        print("Parent-Collection erfolgreich erstellt.")

    def _store_parent_chunks(
        self, parent_chunks: List[ParentChunk]
    ) -> tuple[int, List[str]]:
        """Speichert Parent-Chunks ohne Vektoren."""
        errors: List[str] = []
        if not parent_chunks:
            return 0, errors
        points = [
            PointStruct(
                id=pc.id,
                vector={},
                payload={"text": pc.text, **pc.meta},
            )
            for pc in parent_chunks
        ]
        try:
            self.client.upsert(collection_name=self._parent_collection, points=points)
            print(f"Parent-Collection: {len(points)} Punkte gespeichert.")
            return len(points), errors
        except Exception as e:
            errors.append(f"Parent-Upsert fehlgeschlagen: {e}")
            return 0, errors

    def run(
        self,
        data: List[EmbeddedChunk],
        source_path: str = "",
        parent_chunks: Optional[List[ParentChunk]] = None,  # ← NEU
    ) -> IngestionResult:
        start = time.time()
        errors: List[str] = []
        stored = 0

        # Parent-Chunks zuerst speichern damit IDs bei Fehleranalyse stimmen
        parent_stored, parent_errors = 0, []
        parent_total = len(parent_chunks) if parent_chunks else 0
        if parent_chunks:
            parent_stored, parent_errors = self._store_parent_chunks(parent_chunks)
            errors.extend(parent_errors)

        # Child-Chunks mit Vektoren
        points = []
        for ec in data:
            try:
                vector_dict = {"dense": ec.dense_vector}
                if self.config.use_sparse and hasattr(ec, "sparse_vector") and ec.sparse_vector:
                    vector_dict["sparse"] = SparseVector(
                        indices=list(ec.sparse_vector.keys()),
                        values=list(ec.sparse_vector.values()),
                    )
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector_dict,
                    payload={
                        "text": ec.chunk.text,
                        **ec.chunk.meta,
                        "parent_doc_id": ec.chunk.parent_id,  # ← NEU: Verweis auf Parent
                        **({"context_preamble": ec.context_preamble}
                           if ec.context_preamble else {}),
                    },
                )
                points.append(point)
            except Exception as e:
                errors.append(f"Punkt-Erstellung fehlgeschlagen: {e}")

        if points:
            try:
                self.client.upsert(collection_name=self.config.collection_name, points=points)
                stored = len(points)
                print(f"Gespeichert: {stored} Child-Punkte in '{self.config.collection_name}'.")
            except Exception as e:
                errors.append(f"Upsert fehlgeschlagen: {e}")

        return IngestionResult(
            source_path=source_path,
            chunks_total=len(data),
            chunks_stored=stored,
            parent_chunks_total=parent_total,    # ← NEU
            parent_chunks_stored=parent_stored,  # ← NEU
            collection_name=self.config.collection_name,
            duration_seconds=round(time.time() - start, 2),
            errors=errors,
        )
        

global_ctx = GlobalRunContext(
    output_path="/app/output",
    save_markdown=True,
    save_chunks=True,
    save_parent_chunks=True,
    save_embeddings=True,
    save_ingestion_result=True,
)

extract_input = Extract_Input(
    source_pdf="/app/2024-nachhaltigkeitsbericht.pdf",
    page_range=True,
    first_page=160,
    last_page=190,
)

# 1. Extraktion
extracted_document = Extract_Docling(Extract_Config()).run(extract_input)
save_markdown(extract_input, extracted_document, global_ctx)

# 2. Chunking
chunked_document = Chunk_Docling(ChunkConfig()).run(extracted_document)
save_chunks(extract_input, chunked_document, global_ctx)

# 3. Contextualization 
chunked_document = Contextualize_Qwen(ContextualizeConfig()).run(chunked_document)
save_contextualized_chunks(extract_input, chunked_document, global_ctx)
save_parent_chunks(extract_input, chunked_document, global_ctx) 

# 4. Embedding
embedded_chunks = Embed_BGE(EmbedConfig()).run(chunked_document)
save_embeddings(extract_input, embedded_chunks, global_ctx)

# 5. Speichern
result = Store_Qdrant(StoreConfig(collection_name="iu")).run(
    embedded_chunks,
    source_path=extract_input.source_pdf,
    parent_chunks=chunked_document.parent_chunks,    
)
save_ingestion_result(extract_input, result, global_ctx)

print(result)
