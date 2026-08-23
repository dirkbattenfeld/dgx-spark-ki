"""
Retrieval-Pipeline: Query → Embed → Search → Rerank → Parent-Docs → Generate

Gleicher Stil wie die Ingestion-Pipeline:
- Pydantic-Datenklassen für Config / Input / Output
- ClassVar CONFIG_CLASS / INPUT_CLASS / OUTPUT_CLASS pro Stufe
- Persistierungsfunktionen für jeden Zwischenschritt
- Strukturiertes Logging statt print()
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

import requests
from openai import OpenAI
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import ScoredPoint, NamedVector

# ── Logging ──────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("retrieval")


# ── Globaler Run-Kontext ──────────────────────────────────────────────────────────

class GlobalRunContext(BaseModel):
    output_path: str = "/app/output"
    save_embedded_query: bool = False
    save_search_results: bool = False
    save_reranked_results: bool = False
    save_final_prompt: bool = False
    save_generation_result: bool = False


def _output_dir(global_ctx: GlobalRunContext) -> Path:
    d = Path(global_ctx.output_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _query_stem(query: str) -> str:
    """Dateiname-sicherer Bezeichner aus Query + Timestamp."""
    safe = "".join(c if c.isalnum() else "_" for c in query[:40]).strip("_")
    return f"query_{safe}_{int(time.time())}"


# ─────────────────────────────────────────────────────────────────────────────────
# Datenklassen
# ─────────────────────────────────────────────────────────────────────────────────

class QueryInput(BaseModel):
    """Eingabe für die gesamte Retrieval-Pipeline."""
    query: str
    top_n: int = 20     # Kandidaten aus Qdrant vor Reranking
    top_n1: int = 5     # Finale Treffer nach Reranking → ans LLM


class EmbeddedQuery(BaseModel):
    """Query-Embeddings aus dem Infinity-Service."""
    query: str
    dense_vector: List[float]
    sparse_vector: Dict[int, float] = Field(default_factory=dict)


class SearchHit(BaseModel):
    """Ein einzelner Treffer aus Qdrant."""
    id: str
    score: float
    text: str
    context_preamble: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Rohe Suchtreffer aus Qdrant, vor dem Reranking."""
    query: str
    hits: List[SearchHit]
    duration_seconds: float


class RerankHit(BaseModel):
    """Ein nach Relevanz neu geordneter Treffer."""
    original_hit: SearchHit
    rerank_score: float
    rank: int


class RerankResult(BaseModel):
    """Rerankte Treffer, absteigend nach rerank_score."""
    query: str
    hits: List[RerankHit]
    duration_seconds: float


class EnrichedHit(BaseModel):
    """
    Treffer angereichert mit Parent-Doc-Text.
    parent_text und parent_id sind None solange die Ingestion-Pipeline
    keine Parent-Doc-Verlinkung im Qdrant-Payload speichert.
    """
    rerank_hit: RerankHit
    parent_text: Optional[str] = None
    parent_id: Optional[str] = None


class EnrichedResult(BaseModel):
    """Suchergebnisse angereichert mit Parent-Dokumenten."""
    query: str
    hits: List[EnrichedHit]


class GenerationResult(BaseModel):
    """Vollständiges Ergebnis der LLM-Generierung inkl. Prompt für Debugging."""
    query: str
    answer: str
    prompt: str                 # vollständiger Prompt – ideal für Prompt-Engineering-Iterationen
    prompt_tokens: int
    completion_tokens: int
    duration_seconds: float
    model: str


# ─────────────────────────────────────────────────────────────────────────────────
# Persistierungsfunktionen
# ─────────────────────────────────────────────────────────────────────────────────

def save_embedded_query(
    query_stem: str,
    embedded_query: EmbeddedQuery,
    global_ctx: GlobalRunContext,
) -> None:
    """Speichert Query-Embeddings als JSON – nur Stichproben, kein voller Vektor."""
    if not global_ctx.save_embedded_query:
        return
    target = _output_dir(global_ctx) / f"{query_stem}_embedded_query.json"
    payload = {
        "query": embedded_query.query,
        "dense_dim": len(embedded_query.dense_vector),
        "sparse_nnz": len(embedded_query.sparse_vector),
        "dense_vector_sample": embedded_query.dense_vector[:8],
        "sparse_vector_sample": {
            str(k): v for k, v in list(embedded_query.sparse_vector.items())[:20]
        },
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"[persist] EmbeddedQuery → {target}")


def save_search_results(
    query_stem: str,
    search_result: SearchResult,
    global_ctx: GlobalRunContext,
) -> None:
    """
    Speichert Qdrant-Rohtreffer als JSONL.
    Ideal um zu prüfen ob semantisch sinnvolle Kandidaten gefunden wurden,
    bevor der Reranker die Reihenfolge verändert.
    """
    if not global_ctx.save_search_results:
        return
    target = _output_dir(global_ctx) / f"{query_stem}_search_results.jsonl"
    with target.open("w", encoding="utf-8") as f:
        for hit in search_result.hits:
            f.write(json.dumps(hit.model_dump(), ensure_ascii=False) + "\n")
    logger.info(f"[persist] {len(search_result.hits)} SearchHits → {target}")


def save_reranked_results(
    query_stem: str,
    rerank_result: RerankResult,
    global_ctx: GlobalRunContext,
) -> None:
    """
    Speichert Reranking-Ergebnis als JSONL mit original_score vs. rerank_score –
    so lässt sich der Einfluss des Rerankers direkt beurteilen.
    """
    if not global_ctx.save_reranked_results:
        return
    target = _output_dir(global_ctx) / f"{query_stem}_reranked.jsonl"
    with target.open("w", encoding="utf-8") as f:
        for hit in rerank_result.hits:
            record = {
                "rank": hit.rank,
                "rerank_score": hit.rerank_score,
                "original_score": hit.original_hit.score,
                "text": hit.original_hit.text,
                "headings": hit.original_hit.meta.get("headings", []),
                "page_numbers": hit.original_hit.meta.get("page_numbers", []),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info(f"[persist] {len(rerank_result.hits)} RerankHits → {target}")


def save_generation_result(
    query_stem: str,
    result: GenerationResult,
    global_ctx: GlobalRunContext,
) -> None:
    """
    Speichert GenerationResult als JSON inkl. vollständigem Prompt.
    Zwei separate Dateien: Antwort als lesbares .txt, Rest als .json.
    """
    if not global_ctx.save_generation_result:
        return
    out = _output_dir(global_ctx)

    # Vollständiges Ergebnis als JSON
    json_target = out / f"{query_stem}_generation_result.json"
    json_target.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    # Prompt separat für einfache Lesbarkeit
    if global_ctx.save_final_prompt:
        prompt_target = out / f"{query_stem}_prompt.txt"
        prompt_target.write_text(result.prompt, encoding="utf-8")
        logger.info(f"[persist] Prompt → {prompt_target}")

    logger.info(f"[persist] GenerationResult → {json_target}")


# ─────────────────────────────────────────────────────────────────────────────────
# Stufe 1 – Query einbetten
# ─────────────────────────────────────────────────────────────────────────────────

class QueryEmbedConfig(BaseModel):
    model_name: str = "BAAI/bge-m3"
    api_base: str = "http://gx10:7997"
    return_sparse: bool = False     # Aktivieren sobald Infinity Sparse stabil liefert


class Embed_Query:
    """
    Bettet die User-Query mit dem Infinity-Service ein.

    Der Query-Text wird identisch behandelt wie Chunk-Texte in der
    Ingestion-Pipeline – gleicher Endpunkt, gleiches Modell, keine
    zusätzliche Normalisierung. Nur so stimmt der gemeinsame Vektorraum.

    Sparse-Embeddings werden parallel abgefragt sobald return_sparse=True,
    scheitern aber silent mit einem Warning wenn Infinity keinen Sparse-
    Endpunkt bereitstellt (z.B. bei --engine optimum / ONNX-Backend).
    """
    CONFIG_CLASS: ClassVar[type] = QueryEmbedConfig
    INPUT_CLASS: ClassVar[type] = QueryInput
    OUTPUT_CLASS: ClassVar[type] = EmbeddedQuery

    def __init__(self, config: QueryEmbedConfig):
        self.config = config
        logger.info(
            f"[Embed_Query] Infinity: {config.api_base} | Modell: {config.model_name} | "
            f"Sparse: {'aktiv' if config.return_sparse else 'inaktiv'}"
        )

    def run(self, data: QueryInput) -> EmbeddedQuery:
        logger.info(f"[Embed_Query] Bette Query ein: '{data.query[:80]}'")
        start = time.time()

        # Dense Embedding
        resp = requests.post(
            f"{self.config.api_base}/embeddings",
            json={"model": self.config.model_name, "input": [data.query]},
        )
        resp.raise_for_status()
        dense_vector: List[float] = resp.json()["data"][0]["embedding"]

        # Sparse Embedding (optional)
        sparse_vector: Dict[int, float] = {}
        if self.config.return_sparse:
            try:
                sresp = requests.post(
                    f"{self.config.api_base}/embeddings",
                    json={
                        "model": self.config.model_name,
                        "input": [data.query],
                        "embedding_type": "sparse",
                    },
                    timeout=10,
                )
                sresp.raise_for_status()
                raw = sresp.json()["data"][0]["embedding"]
                sparse_vector = {int(k): float(v) for k, v in raw.items()}
                logger.debug(f"[Embed_Query] Sparse: {len(sparse_vector)} non-zero Einträge")
            except requests.HTTPError as e:
                logger.warning(f"[Embed_Query] Sparse-Embedding nicht verfügbar: {e}")

        elapsed = round(time.time() - start, 3)
        logger.info(
            f"[Embed_Query] Abgeschlossen in {elapsed}s | "
            f"Dense-Dim: {len(dense_vector)} | Sparse-NNZ: {len(sparse_vector)}"
        )

        return EmbeddedQuery(
            query=data.query,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
        )


# ─────────────────────────────────────────────────────────────────────────────────
# Stufe 2 – Semantische Suche in Qdrant
# ─────────────────────────────────────────────────────────────────────────────────

class SearchConfig(BaseModel):
    host: str = "ryzon9"
    port: int = 6333
    collection_name: str = "iu"
    score_threshold: Optional[float] = None     # None = kein Score-Filter


class Search_Qdrant:
    """
    Sucht die top-n semantisch ähnlichsten Chunks in Qdrant.

    Nutzt den 'dense' Named-Vector-Index aus der Ingestion-Pipeline.
    Hybrid-Search (dense + sparse via Reciprocal Rank Fusion) ist
    vorbereitet und wird aktiviert sobald Infinity Sparse-Vektoren liefert:
    Dazu client.search() durch client.query_points() mit PrefetchQuery
    ersetzen und den fusion-Parameter auf models.Fusion.RRF setzen.

    top_n kommt aus QueryInput und nicht aus SearchConfig, damit er
    zusammen mit top_n1 zentral am Einstiegspunkt der Pipeline gesteuert wird.
    """
    CONFIG_CLASS: ClassVar[type] = SearchConfig
    INPUT_CLASS: ClassVar[type] = EmbeddedQuery
    OUTPUT_CLASS: ClassVar[type] = SearchResult

    def __init__(self, config: SearchConfig):
        self.config = config
        self.client = QdrantClient(host=config.host, port=config.port)
        logger.info(
            f"[Search_Qdrant] Verbunden mit {config.host}:{config.port} | "
            f"Collection: {config.collection_name}"
        )

    def run(self, data: EmbeddedQuery, top_n: int = 20) -> SearchResult:
        logger.info(
            f"[Search_Qdrant] Suche top-{top_n} in '{self.config.collection_name}' | "
            f"Query: '{data.query[:60]}'"
        )
        start = time.time()

        raw_results: List[ScoredPoint] = self.client.query_points(
            collection_name=self.config.collection_name,
            query=data.dense_vector,
            using="dense",
            limit=top_n,
            score_threshold=self.config.score_threshold,
            with_payload=True,
        ).points

        hits: List[SearchHit] = []
        for point in raw_results:
            payload = point.payload or {}
            hits.append(SearchHit(
                id=str(point.id),
                score=point.score,
                text=payload.get("text", ""),
                context_preamble=payload.get("context_preamble"),
                meta={k: v for k, v in payload.items() if k not in ("text", "context_preamble")},
            ))

        elapsed = round(time.time() - start, 3)
        if hits:
            logger.info(
                f"[Search_Qdrant] {len(hits)} Treffer in {elapsed}s | "
                f"Score-Range: [{hits[-1].score:.3f} – {hits[0].score:.3f}]"
            )
        else:
            logger.warning(f"[Search_Qdrant] Keine Treffer gefunden ({elapsed}s)")

        return SearchResult(query=data.query, hits=hits, duration_seconds=elapsed)


# ─────────────────────────────────────────────────────────────────────────────────
# Stufe 3 – Cross-Encoder Reranking
# ─────────────────────────────────────────────────────────────────────────────────

class RerankConfig(BaseModel):
    api_base: str = "http://gx10:7997"
    # Reranker-Modell separat in Infinity registrieren, z.B.:
    # infinity_emb start --model-name-or-path BAAI/bge-reranker-v2-m3 --port 7997
    model_name: str = "BAAI/bge-reranker-v2-m3"


class Rerank_BGE:
    """
    Ordnet die Qdrant-Kandidaten mit einem Cross-Encoder neu.

    Cross-Encoder-Reranker unterscheiden sich fundamental vom Bi-Encoder:
    Sie bewerten Query und Passage *gemeinsam* in einem einzigen
    Forward-Pass. Das ist teurer (O(n) Inferences statt O(1)), aber
    deutlich präziser – der Reranker versteht die Beziehung zwischen
    Query und Text, nicht nur die geometrische Nähe im Vektorraum.

    BGE-Reranker-v2-m3 ist multilingual und für RAG-Reranking optimiert.
    Infinity stellt dafür den /rerank-Endpunkt bereit (OpenAI-kompatibel).

    top_n1 kommt aus QueryInput um konsistente Pipeline-Steuerung zu
    gewährleisten – SearchResult enthält top_n, Reranking reduziert auf top_n1.
    """
    CONFIG_CLASS: ClassVar[type] = RerankConfig
    INPUT_CLASS: ClassVar[type] = SearchResult
    OUTPUT_CLASS: ClassVar[type] = RerankResult

    def __init__(self, config: RerankConfig):
        self.config = config
        logger.info(f"[Rerank_BGE] Reranker: {config.model_name} @ {config.api_base}")

    def run(self, data: SearchResult, top_n1: int = 5) -> RerankResult:
        logger.info(f"[Rerank_BGE] Reranke {len(data.hits)} Kandidaten → top-{top_n1}")
        start = time.time()

        documents = [hit.text for hit in data.hits]

        resp = requests.post(
            f"{self.config.api_base}/rerank",
            json={
                "model": self.config.model_name,
                "query": data.query,
                "documents": documents,
                "top_n": top_n1,
                "return_documents": False,      # Text liegt bereits in data.hits vor
            },
        )
        resp.raise_for_status()

        # Infinity liefert [{index: int, relevance_score: float}, ...]
        # bereits absteigend nach relevance_score sortiert
        reranked_hits: List[RerankHit] = []
        for rank, item in enumerate(resp.json()["results"], start=1):
            original_hit = data.hits[item["index"]]
            reranked_hits.append(RerankHit(
                original_hit=original_hit,
                rerank_score=item["relevance_score"],
                rank=rank,
            ))

        elapsed = round(time.time() - start, 3)
        scores = [h.rerank_score for h in reranked_hits]
        logger.info(
            f"[Rerank_BGE] Abgeschlossen in {elapsed}s | "
            f"Score-Range: [{min(scores):.3f} – {max(scores):.3f}]"
        )

        return RerankResult(query=data.query, hits=reranked_hits, duration_seconds=elapsed)


# ─────────────────────────────────────────────────────────────────────────────────
# Stufe 4 – Parent-Dokumente aus Qdrant laden
# ─────────────────────────────────────────────────────────────────────────────────

class ParentDocConfig(BaseModel):
    host: str = "ryzon9"
    port: int = 6333
    collection_name: str = "iu_parents"
    # Name des Payload-Felds in dem die Ingestion-Pipeline die Parent-Doc-ID
    # ablegt. Wird befüllt sobald Ingestion Parent-Docs als separate Qdrant-
    # Punkte speichert und den Verweis im Chunk-Payload hinterlegt.
    parent_id_field: str = "parent_doc_id"
    fetch_parent: bool = True      # Umstellen sobald Parent-Docs in Qdrant verlinkt sind


class FetchParentDocs_Qdrant:
    """
    Holt für jeden Reranking-Treffer das zugehörige Parent-Dokument.

    Das Konzept: Chunks sind klein (≤512 Tokens) – gut für präzises Matching.
    Das LLM braucht aber mehr Kontext. Parent-Docs sind größere Einheiten
    (z.B. ganze Seiten oder Abschnitte) die im Payload-Feld parent_doc_id
    referenziert werden.

    Voraussetzungen für fetch_parent=True:
    ① Ingestion-Pipeline speichert für jeden Chunk 'parent_doc_id' im Payload
    ② Parent-Dokumente existieren als eigene Qdrant-Punkte (gleiche oder
       separate Collection)
    ③ parent_doc_id enthält den Qdrant-Point-UUID des Parent-Punkts

    Solange fetch_parent=False: Chunk-Text wird direkt an Generate weitergereicht.
    Die EnrichedHit-Struktur ist für das spätere Upgrade bereits vollständig.
    """
    CONFIG_CLASS: ClassVar[type] = ParentDocConfig
    INPUT_CLASS: ClassVar[type] = RerankResult
    OUTPUT_CLASS: ClassVar[type] = EnrichedResult

    def __init__(self, config: ParentDocConfig):
        self.config = config
        if config.fetch_parent:
            self.client = QdrantClient(host=config.host, port=config.port)
            logger.info(
                f"[FetchParentDocs] Verbunden mit {config.host}:{config.port} | "
                f"fetch_parent=True | parent_id_field='{config.parent_id_field}'"
            )
        else:
            self.client = None
            logger.info("[FetchParentDocs] fetch_parent=False – Chunk-Text wird direkt genutzt")

    def run(self, data: RerankResult) -> EnrichedResult:
        logger.info(f"[FetchParentDocs] Verarbeite {len(data.hits)} Reranking-Treffer")
        enriched_hits: List[EnrichedHit] = []

        for rerank_hit in data.hits:
            parent_text: Optional[str] = None
            parent_id: Optional[str] = rerank_hit.original_hit.meta.get(self.config.parent_id_field)

            if self.config.fetch_parent and parent_id and self.client:
                try:
                    points = self.client.retrieve(
                        collection_name=self.config.collection_name,
                        ids=[parent_id],
                        with_payload=True,
                    )
                    if points:
                        parent_text = (points[0].payload or {}).get("text")
                        logger.debug(
                            f"[FetchParentDocs] Parent-Doc geladen: {parent_id} "
                            f"({len(parent_text or '')} Zeichen)"
                        )
                    else:
                        logger.warning(f"[FetchParentDocs] Parent-Doc nicht gefunden: {parent_id}")
                except Exception as e:
                    logger.warning(f"[FetchParentDocs] Fehler bei Parent-Doc {parent_id}: {e}")

            enriched_hits.append(EnrichedHit(
                rerank_hit=rerank_hit,
                parent_text=parent_text,
                parent_id=parent_id,
            ))

        fetched = sum(1 for h in enriched_hits if h.parent_text is not None)
        logger.info(
            f"[FetchParentDocs] Abgeschlossen | "
            f"Parent-Docs geladen: {fetched}/{len(enriched_hits)}"
        )

        return EnrichedResult(query=data.query, hits=enriched_hits)


# ─────────────────────────────────────────────────────────────────────────────────
# Stufe 5 – Prompt bauen und LLM aufrufen
# ─────────────────────────────────────────────────────────────────────────────────

class GenerateConfig(BaseModel):
    base_url: str = "http://gx10:8888/v1"
    api_key: str = "no-key"
    model: str = "Qwen/Qwen2.5-Coder-3B-Instruct"         # nvidia/Qwen3-Next-80B-A3B-Instruct-NVFP4" 
    max_tokens: int = 2048
    temperature: float = 0.1
    no_think: bool = False          # True für /no_think bei Qwen3 (kein CoT)
    max_context_chars: int = 12000  # Sicherheitslimit Kontext im Prompt
    system_prompt: str = (
        "Du bist ein präziser Dokumentenassistent. "
        "Beantworte die Frage ausschließlich auf Basis der bereitgestellten Kontextabschnitte. "
        "Wenn die Antwort im Kontext nicht enthalten ist, sage das klar. "
        "Belege deine Aussagen wo möglich mit den Abschnittsnummern in eckigen Klammern."
    )


class Generate_Qwen:
    """
    Baut den RAG-Prompt und ruft das LLM über den vLLM OpenAI-Endpunkt auf.

    Prompt-Struktur:
        SYSTEM  – Rolle und Verhaltensvorgaben
        USER    – Nummerierte Kontextabschnitte + Frage

    Kontext pro Abschnitt:
        [N] Heading > Subheading (S. X)
        <text>

    Der Kontext nutzt parent_text wenn vorhanden (größere Einheit mit
    mehr Zusammenhang), ansonsten chunk.text direkt. Das max_context_chars-
    Limit verhindert Prompt-Overflow bei vielen oder langen Treffern –
    Abschnitte die das Limit überschreiten werden übersprungen und geloggt.
    """
    CONFIG_CLASS: ClassVar[type] = GenerateConfig
    INPUT_CLASS: ClassVar[type] = EnrichedResult
    OUTPUT_CLASS: ClassVar[type] = GenerationResult

    def __init__(self, config: GenerateConfig):
        self.config = config
        self.client = OpenAI(base_url=config.base_url, api_key=config.api_key)
        logger.info(f"[Generate_Qwen] vLLM: {config.base_url} | Modell: {config.model}")

    def _build_context_block(self, hits: List[EnrichedHit]) -> str:
        parts: List[str] = []
        total_chars = 0

        for i, ehit in enumerate(hits, start=1):
            # Parent-Text bevorzugen, Chunk-Text als Fallback
            text = ehit.parent_text or ehit.rerank_hit.original_hit.text
            headings = ehit.rerank_hit.original_hit.meta.get("headings", [])
            pages = ehit.rerank_hit.original_hit.meta.get("page_numbers", [])

            header = f"[{i}]"
            if headings:
                header += f" {' > '.join(headings)}"
            if pages:
                header += f" (S. {', '.join(str(p) for p in pages)})"

            block = f"{header}\n{text}"

            if total_chars + len(block) > self.config.max_context_chars:
                logger.warning(
                    f"[Generate_Qwen] Kontext-Limit erreicht bei Abschnitt {i} "
                    f"({total_chars}/{self.config.max_context_chars} Zeichen) – übersprungen"
                )
                continue

            parts.append(block)
            total_chars += len(block)

        logger.debug(
            f"[Generate_Qwen] Kontextblock: {len(parts)} Abschnitte, {total_chars} Zeichen"
        )
        return "\n\n---\n\n".join(parts)

    def _build_user_message(self, query: str, context_block: str) -> str:
        no_think_suffix = " /no_think" if self.config.no_think else ""
        return (
            f"Hier sind die relevanten Kontextabschnitte:\n\n"
            f"{context_block}\n\n"
            f"---\n\n"
            f"Frage: {query}{no_think_suffix}"
        )

    def run(self, data: EnrichedResult) -> GenerationResult:
        logger.info(
            f"[Generate_Qwen] Generiere Antwort | "
            f"Kontext: {len(data.hits)} Abschnitte | Query: '{data.query[:60]}'"
        )
        start = time.time()

        context_block = self._build_context_block(data.hits)
        user_message = self._build_user_message(data.query, context_block)
        full_prompt = f"SYSTEM:\n{self.config.system_prompt}\n\nUSER:\n{user_message}"

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

        answer = response.choices[0].message.content.strip()
        usage = response.usage
        elapsed = round(time.time() - start, 2)

        logger.info(
            f"[Generate_Qwen] Abgeschlossen in {elapsed}s | "
            f"Tokens: {usage.prompt_tokens} prompt + {usage.completion_tokens} completion"
        )

        return GenerationResult(
            query=data.query,
            answer=answer,
            prompt=full_prompt,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            duration_seconds=elapsed,
            model=self.config.model,
        )


# ─────────────────────────────────────────────────────────────────────────────────
# Einstiegspunkt
# ─────────────────────────────────────────────────────────────────────────────────

global_ctx = GlobalRunContext(
    output_path="/app/output",
    save_embedded_query=True,
    save_search_results=True,
    save_reranked_results=True,
    save_final_prompt=True,
    save_generation_result=True,
)

query_input = QueryInput(
    query="Welche THG Emissionen werden für 2024 genannt? Differenziere nach Scopes!",
    top_n=20,
    top_n1=5,
)

stem = _query_stem(query_input.query)

# 1. Query einbetten
embedded_query = Embed_Query(QueryEmbedConfig()).run(query_input)
save_embedded_query(stem, embedded_query, global_ctx)

# 2. Semantische Suche in Qdrant
search_result = Search_Qdrant(SearchConfig()).run(embedded_query, top_n=query_input.top_n)
save_search_results(stem, search_result, global_ctx)

# 3. Cross-Encoder Reranking
rerank_result = Rerank_BGE(RerankConfig()).run(search_result, top_n1=query_input.top_n1)
save_reranked_results(stem, rerank_result, global_ctx)

# 4. Parent-Docs laden (Platzhalter – fetch_parent=False bis Ingestion Parent-IDs speichert)
enriched_result = FetchParentDocs_Qdrant(ParentDocConfig()).run(rerank_result)

# 5. Antwort generieren
generation_result = Generate_Qwen(GenerateConfig()).run(enriched_result)
save_generation_result(stem, generation_result, global_ctx)

logger.info(f"\n{'='*60}\nFrage: {generation_result.query}\n\nAntwort:\n{generation_result.answer}\n{'='*60}")