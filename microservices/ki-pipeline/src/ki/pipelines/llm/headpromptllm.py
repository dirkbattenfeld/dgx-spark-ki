import logging

from ki.pipelines.llm.questionselector import QuestionEntry, HeadPromptLlmInput

from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Any, ClassVar
from pydantic import BaseModel 

from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.promptfactory import PromptConfig
from ki.llm import LlmConfig, clean_antwort_llm
from ki_dgxsdk.ki_dgxsdk import DGX_Client

import time

class HeadPromptLlmConfig(BaseModel):
    prompt: PromptConfig
    llm_config: LlmConfig
    devices: List[str] = ["gpu", "cpu"]
    write_artifact: bool = True

@dataclass
class HeadPromptLlmRunContext(BaseRunContext[HeadPromptLlmConfig]):
    component_name: str
    config: HeadPromptLlmConfig
    component_path: Optional[Path] = None

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )

class HeadPromptLlmResult(BaseComponentResult):
    entries: List[QuestionEntry]
    _pipeline_outputs: ClassVar[list[str]] = ['entries']   
        
    class ConfigDict:
        default_serializer = "pydantic_json"

@component_registry.register("head_prompt_llm")
class HeadPromptLlm(BaseComponent):    
    CONFIG_CLASS = HeadPromptLlmConfig
    INPUT_CLASS = HeadPromptLlmInput
    OUTPUT_CLASS = HeadPromptLlmResult
    RUN_CONTEXT_CLASS = HeadPromptLlmRunContext
    
    def __init__(
        self,
        *,
        config: HeadPromptLlmConfig,
        global_build_ctx: GlobalBuildContext):
     
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)

        # Microservice für LLM bauen
        self.dgx_llm = DGX_Client(job_type="text")

    def run(self, data, *, component_ctx, global_ctx):
        run_logger = global_ctx.run_logger
        context = """You are a helpful assistant. Provide only the factual truth. 
        Do not mention myths, misconceptions, or common beliefs, even to debunk them. 
        Do not provide any conversational filler or introductory phrases. 
        If a question is based on a false premise, state the correct fact directly 
        without referring to the false premise. Question: """

        for entry in data.entries:
            start = time.time()
            final_prompt = context + entry.question 
            result = self.dgx_llm.generate(
                prompt=final_prompt,
                temperature=0.1
                )
            dauer = time.time() - start
            answer = result.get("answer")
            # Antwort in das Objekt schreiben
            entry.llm_response = answer
            entry.llm_time_used = dauer
    
        run_logger.info(f"Inferenz für {len(data.entries)} Fragen abgeschlossen.")
    
        results = HeadPromptLlmResult(
            entries=data.entries,
        )

        return results





