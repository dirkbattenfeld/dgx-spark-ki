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
             
        # PromptFactory setzen
        self.prompt_factory = self.global_build_ctx.prompt_factory
        if not self.prompt_factory:
            raise ValueError("PromptFactory instance must be provided")
        
        # Prompt-Objekt bauen über Factory
        self.prompt_obj = self.prompt_factory.build_prompt(self.config)
        

    def run(self, data, *, component_ctx, global_ctx):
        run_logger = global_ctx.run_logger
        for entry in data.entries:
            start = time.time()
            answer = clean_antwort_llm(self.prompt_obj.execute(
                entry.question,
                component_ctx.config.prompt,
                component_ctx.config.llm_config))
            dauer = time.time() - start
            
            # Antwort in das Objekt schreiben
            entry.llm_response = answer
            entry.llm_time_used = dauer
    
        run_logger.info(f"Inferenz für {len(data.entries)} Fragen abgeschlossen.")
    
        results = HeadPromptLlmResult(
            entries=data.entries,
        )

        return results





