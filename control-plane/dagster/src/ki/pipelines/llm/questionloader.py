from pathlib import Path
from typing import Any 
from dataclasses import dataclass
from pydantic import BaseModel 
import json

from ki.pipelines.base.registry import component_registry
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext
from ki.pipelines.base import BaseComponent, BaseComponentResult

# todo: verschiedene Loader:
# - Testfragen in der Config im YAML

class QuestionLoaderConfig(BaseModel):
    datafilepath: Path

class Document(BaseComponentResult):
    document: Any

@dataclass
class QuestionLoaderRunContext(BaseRunContext[QuestionLoaderConfig]):
    component_name: str
    config: QuestionLoaderConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )
    
@component_registry.register("questionloader")
class QuestionLoader(BaseComponent):    
    CONFIG_CLASS = QuestionLoaderConfig
    INPUT_CLASS = None
    OUTPUT_CLASS = Document
    RUN_CONTEXT_CLASS = QuestionLoaderRunContext

    def __init__(
        self,
        *,
        config: QuestionLoaderConfig,
        global_build_ctx: GlobalBuildContext):
         
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
    
    def run(self, data, *, component_ctx = None, global_ctx = None):
        datafilepath = component_ctx.config.datafilepath
        with open(datafilepath, "r") as f:
            readdata = json.load(f)
        return Document(document=readdata)

