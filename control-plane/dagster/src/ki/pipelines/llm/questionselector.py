from ki.pipelines.llm.questionloader import Document
import logging

from dataclasses import dataclass
from typing import List, Optional, ClassVar
from pydantic import BaseModel 

from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base import BaseComponent, BaseComponentResult

# todo: File lesen oder Testoption mit festen questions
# todo: Logik von RAG/Eval adaptieren mit batches und automatischer Fortsetzung  
# Konfigurationsklasse für TestQuestionLoader

class QuestionSelectorConfig(BaseModel):
    start: int
    end: int

class QuestionEntry(BaseModel):
    index: int
    question: str
    correct_answers: List[str] = []
    incorrect_answers: List[str] = []
    type: str
    category: str
    llm_response: Optional[str] = None
    llm_time_used: Optional[float] = None

class HeadPromptLlmInput(BaseComponentResult):
    entries: List[QuestionEntry]
    _drop_outputs: ClassVar[list[str]] = ['entries'] 
    
@dataclass
class QuestionSelectorRunContext(BaseRunContext[QuestionSelectorConfig]):
    component_name: str
    config: QuestionSelectorConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )
        
@component_registry.register("questionselector")
class QuestionSelector(BaseComponent):    
    CONFIG_CLASS = QuestionSelectorConfig
    INPUT_CLASS = Document
    OUTPUT_CLASS = HeadPromptLlmInput
    RUN_CONTEXT_CLASS = QuestionSelectorRunContext

    def __init__(
        self,
        *,
        config: QuestionSelectorConfig,
        global_build_ctx: GlobalBuildContext):
         
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
    
    def run(self, data, *, component_ctx = None, global_ctx = None):
        entries = []
        for i in range(component_ctx.config.start, component_ctx.config.end + 1):
            raw = data.document[i]
            entries.append(QuestionEntry(
                index=i,
                question=raw["question"],
                correct_answers=raw.get("correct_answers", []),
                incorrect_answers=raw.get("incorrect_answers", []),
                type=raw.get("type", []),
                category=raw.get("category", [])
            ))
        return HeadPromptLlmInput(entries=entries)


