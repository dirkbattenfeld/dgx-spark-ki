import time
import httpx

from typing import ClassVar
from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.rag_request.fetchparents import EnrichedResult

# Import EnrichedResult von oben

class GenerationResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _pipeline_outputs: ClassVar[list[str]] = ['query', 'answer', 'prompt', 'duration_seconds', 'model']
    query: str
    answer: str
    prompt: str
    prompt_tokens: int
    completion_tokens: int
    duration_seconds: float
    model: str
    class ConfigDict:
        default_serializer = "pydantic_json"

class GenerateConfig(BaseModel):
    max_tokens: int = 2048
    temperature: float = 0.1
    no_think: bool = False
    max_context_chars: int = 12000
    system_prompt: str = "Du bist ein präziser Dokumentenassistent..."

@dataclass
class GenerateRunContext(BaseRunContext[GenerateConfig]):
    component_name: str
    config: GenerateConfig

@component_registry.register('request_llm')
class GenerateQwen(BaseComponent):
    CONFIG_CLASS: ClassVar[type] = GenerateConfig
    INPUT_CLASS: ClassVar[type] = EnrichedResult
    OUTPUT_CLASS: ClassVar[type] = GenerationResult
    RUN_CONTEXT_CLASS: ClassVar[type] = GenerateRunContext

    def run(self, data: EnrichedResult, *, component_ctx: GenerateRunContext, global_ctx: GlobalRunContext) -> GenerationResult:
        cfg = component_ctx.config
        start = time.time()
        
        # Kontext-Block bauen
        parts = []
        curr_chars = 0
        for i, hit in enumerate(data.hits, 1):
            text = hit.parent_text or hit.rerank_hit.original_hit.text
            meta = hit.rerank_hit.original_hit.meta
            header = f"[{i}] {' > '.join(meta.get('headings', []))} (S. {meta.get('page_numbers', [])})"
            block = f"{header}\n{text}"
            if curr_chars + len(block) < cfg.max_context_chars:
                parts.append(block)
                curr_chars += len(block)

        user_msg = f"Kontext:\n\n{'\n\n---\n\n'.join(parts)}\n\nFrage: {data.query}"
        if cfg.no_think: user_msg += " /no_think"

        with httpx.Client(base_url=global_ctx.infra.vllm_url, timeout=120.0) as client:
            resp = client.post("/chat/completions", json={
                "model": global_ctx.infra.MODEL_LLM,
                "messages": [
                    {"role": "system", "content": cfg.system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens
            })
            resp.raise_for_status()
            res_json = resp.json()

        return GenerationResult(
            query=data.query,
            answer=res_json["choices"][0]["message"]["content"].strip(),
            prompt=user_msg,
            prompt_tokens=res_json["usage"]["prompt_tokens"],
            completion_tokens=res_json["usage"]["completion_tokens"],
            duration_seconds=round(time.time()-start, 2),
            model=global_ctx.infra.MODEL_LLM
        )
