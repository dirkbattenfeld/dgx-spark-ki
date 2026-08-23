# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.18.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
# ki/promptfactory/prompts/contextfreiprompt.py
from __future__ import annotations

from pydantic import BaseModel
from typing import Literal

from langchain_core.prompts import PromptTemplate

from ki.promptfactory.prompts.promptregistry import prompt_registry
from ki.llm.llama import LocalLlamaLLM


# %%
class ContextFreiPromptConfig(BaseModel):
    prompt_type: Literal["context_frei"] = "context_frei"
    context: str = "You are an expert and provide professional answers!"
    template_text: str = "Answer the following question based on the context: {context}. Question: {question}"
    

@prompt_registry.register("context_frei")
class ContextFreiPrompt:
    def __init__(self, llm_config: LlmConfig):
        self.llm_config = llm_config
        self.llm = LocalLlamaLLM(device=self.llm_config.device, config=self.llm_config)

    def execute(self, question: str, prompt: PromptConfig, llm_override: Optional[LlmConfig] = None) -> str:  # === NEU ===
        template_text = prompt.template_text
        prompt_template = PromptTemplate(input_variables=["context","question"], template=template_text)
        full_prompt = prompt_template.format(context=prompt.context, question=question)
        llm_config = llm_override or self.llm_config
        return self.llm._call(full_prompt, llm_override=llm_override)

# %%
