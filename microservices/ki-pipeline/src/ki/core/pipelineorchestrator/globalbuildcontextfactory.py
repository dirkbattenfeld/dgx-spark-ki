# ki/core/pipelineorchestrator/globalbuildcontextfactory.py

from ki.pipelines.base.registry import component_registry
from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext
#from ki.promptfactory.prompts.promptregistry import prompt_registry
#from ki.promptfactory import PromptFactory

import logging
from pathlib import Path


# %%
class GlobalBuildContextFactory:
    def __init__(self, base_path: Path, logger: logging.Logger):
        self.base_path = base_path
        self.logger = logger
        
    def create(self) -> GlobalBuildContext:
        # todo: prompt registry und factory nur bauen, wenn sie auch benötigt werden
        # Registries, Factories, Defaults
#        prompt_factory = PromptFactory(prompt_registry, self.logger)
        
        return GlobalBuildContext(
            component_registry=component_registry,
#            prompt_factory=prompt_factory,
#            prompt_registry=prompt_registry,
            build_logger=self.logger,
            base_path=self.base_path
        )

# %%
