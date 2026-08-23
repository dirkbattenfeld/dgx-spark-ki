import asyncio
import httpx
import time
from typing import ClassVar
from dataclasses import dataclass
from pydantic import BaseModel

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent
from ki.pipelines.rag.chunk import ChunkedDocument, Chunk

class ContextualizeConfig(BaseModel):
    max_tokens: int = 256
    temperature: float = 0.0
    document_window_chars: int = 6000
    max_concurrent: int = 8
    no_think: bool = True

@dataclass
class ContextualizeRunContext(BaseRunContext[ContextualizeConfig]):
    component_name: str
    config: ContextualizeConfig

@component_registry.register('contextualize')
class Contextualize(BaseComponent):
    CONFIG_CLASS: ClassVar[type] = ContextualizeConfig
    INPUT_CLASS: ClassVar[type] = ChunkedDocument
    OUTPUT_CLASS: ClassVar[type] = ChunkedDocument
    RUN_CONTEXT_CLASS: ClassVar[type] = ContextualizeRunContext

    SYSTEM_PROMPT = (
        "Du bist ein präziser Dokumentanalyst. "
        "Deine Aufgabe ist es, einen kurzen Kontext für einen Textabschnitt zu formulieren, "
        "der erklärt wo im Dokument dieser Abschnitt steht und welche Rolle er spielt. "
        "Antworte ausschließlich mit dem Kontext, ohne Einleitung oder Erklärung. "
        "Maximal 2 Sätze."
    )

    def _build_prompt(self, document_window: str, chunk: Chunk, config: ContextualizeConfig) -> str:
        headings = " > ".join(chunk.meta.get("headings", []))
        pages = chunk.meta.get("page_numbers", [])
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
            f"<chunk>\n{chunk.text}\n</chunk>\n\n"
            f"Formuliere einen kurzen Kontext (1-2 Sätze) der erklärt, "
            f"wo im Dokument dieser Chunk steht und welchem Zweck er dient.{no_think_suffix}"
        )

    async def _call_vllm(self, client: httpx.AsyncClient, prompt: str, config: ContextualizeConfig, global_ctx: GlobalRunContext, logger) -> str:
        try:
            response = await client.post(
                "/chat/completions",
                json={
                    "model": global_ctx.infra.MODEL_LLM,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                },
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"vLLM Call fehlgeschlagen: {e}")
            return ""

    def run(self, data: ChunkedDocument, *, component_ctx: ContextualizeRunContext, global_ctx: GlobalRunContext) -> ChunkedDocument:
        run_logger = global_ctx.run_logger
        cfg = component_ctx.config
        start = time.time()
        
        document_window = data.source.markdown_content[:cfg.document_window_chars]
        total = len(data.chunks)
        run_logger.info(f"Starte Contextualization für {total} Chunks (max_concurrent={cfg.max_concurrent}).")

        async def process_all():
            sem = asyncio.Semaphore(cfg.max_concurrent)
            async with httpx.AsyncClient(base_url=global_ctx.infra.vllm_url) as client:
                async def process_one(chunk: Chunk, idx: int):
                    async with sem:
                        prompt = self._build_prompt(document_window, chunk, cfg)
                        preamble = await self._call_vllm(client, prompt, cfg, global_ctx, run_logger)
                        if idx % 20 == 0: run_logger.info(f"  [{idx}/{total}] Chunks verarbeitet...")
                        return preamble
                return await asyncio.gather(*(process_one(c, i) for i, c in enumerate(data.chunks)))

        preambles = asyncio.run(process_all())

        for chunk, preamble in zip(data.chunks, preambles):
            chunk.meta["context_preamble"] = preamble

        elapsed = round(time.time() - start, 1)
        run_logger.info(f"Contextualization abgeschlossen in {elapsed}s.")
        return data
