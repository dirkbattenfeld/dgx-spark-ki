# --- Step 3: Contextualize ---
import logging
import asyncio
import os
from typing import Any, Dict, List

from applications.rag.pipelines.rag_ingestion.steps.configs import ContextualizeConfig
from applications.rag.pipelines.rag_ingestion.steps.models import Chunk, ChunkedDocument

# --- HILFSFUNKTIONEN FÜR DEN VLLM CALL ---
def _build_prompt(document_window: str, chunk: Dict[str, Any], config: ContextualizeConfig) -> str:
    meta = chunk.get("meta", {})
    headings = " > ".join(meta.get("headings", []))
    pages = meta.get("page_numbers", [])
    
    location_hint = ""
    if headings:
        location_hint += f"Abschnittsebene: {headings}\n"
    if pages:
        location_hint += f"Seite(n): {', '.join(str(p) for p in pages)}\n"

    no_think_suffix = " /no_think" if config.no_think else ""

    return (
        f"Hier ist ein Auszug aus dem Dokument als Kontext:\n"
        f"<document>\n{document_window}\n</document>\n\n"
        f"{location_hint}"
        f"Hier ist der Chunk:\n"
        f"<chunk>\n{chunk.get('text', '')}\n</chunk>\n\n"
        f"Formuliere einen kurzen Kontext (1-2 Sätze) der erklärt, "
        f"wo im Dokument dieser Chunk steht und welchem Zweck er dient.{no_think_suffix}"
    )


async def contextualize_action(chunked_doc: ChunkedDocument, vllm_client: Any, config: ContextualizeConfig) -> ChunkedDocument:
    """
    Verarbeitet Chunks asynchron über vLLM.
    """
    logger = logging.getLogger(__name__)
    
    filename = os.path.basename(chunked_doc.source.source_path)
        
    document_window = chunked_doc.source.markdown_content[:config.document_window_chars]
    
    chunks: List[Chunk] = chunked_doc.chunks
    total = len(chunks)
    
    total = len(chunked_doc.chunks)
    logger.info(f"🤖 [Contextualize] Starte vLLM für {total} Chunks (max_concurrent={config.max_concurrent}) von {filename}...")

    # Semaphor für Concurrency-Steuerung innerhalb des Dokuments
    sem = asyncio.Semaphore(config.max_concurrent)
    
    async def process_one(chunk: Chunk, idx: int):
        async with sem:
            prompt = _build_prompt(document_window, chunk.model_dump(), config)
            try:
                response = await vllm_client.chat_async(
                    prompt=prompt,
                    system_prompt="Du bist ein präziser Dokumentanalyst. Maximal 2 Sätze.",
                    max_tokens=config.max_tokens,
                    temperature=config.temperature
                )
                preamble = response.get("text", "").strip()
            except Exception as e:
                logger.error(f"💥 vLLM Fehler bei Chunk {idx}: {e}")
                preamble = ""
            
            # Direkt in die Struktur schreiben (In-Memory-Mutation)
            chunk.meta["context_preamble"] = preamble
            return chunk

    # Alle Sub-Requests parallel abfeuern
    tasks = [process_one(c, i) for i, c in enumerate(chunks)]
    chunked_doc.chunks = await asyncio.gather(*tasks)

    # Rückgabe des modifizierten ChunkedDocument-Äquivalents
    chunked_doc.status = "success"
    return chunked_doc
