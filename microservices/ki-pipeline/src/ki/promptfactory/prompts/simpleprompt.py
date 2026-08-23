# ki.promptfactory/prompts/simpleprompt.py
from __future__ import annotations

from pydantic import BaseModel
from typing import Literal
from langchain_core.prompts import PromptTemplate

from ki.promptfactory.prompts.promptregistry import prompt_registry
from ki.llm.llama import LocalLlamaLLM


# %%
class SimplePromptConfig(BaseModel):
    prompt_type: Literal["simple"] = "simple"

@prompt_registry.register("simple")
class SimplePrompt:
    def __init__(self, llm_config: LlmConfig):
        # === NEU: Nur LLM-Parameter, kein Template mehr ===
        self.llm_config = llm_config
        self.llm = LocalLlamaLLM(device=self.llm_config.device, config=self.llm_config)

    def execute(self, question: str, prompt: PromptConfig, llm_override: Optional[LlmConfig] = None) -> str:  # === NEU: nur prompt + override ===
        # === NEU: Template erst hier bauen aus Runtime-Prompt ===
        template_text = "{question}"
        prompt_template = PromptTemplate(input_variables=["question"], template=template_text)
        full_prompt = prompt_template.format(question=question)
        llm_config = llm_override or self.llm_config
        return self.llm._call(full_prompt, llm_override=llm_override)

# %%
