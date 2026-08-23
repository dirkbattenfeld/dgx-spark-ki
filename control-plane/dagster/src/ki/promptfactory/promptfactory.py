# ki.promptfactory.promptfactory.py

from typing import Protocol, Union
import logging

# todo: beseitigen durch Interface?
from ki.core.base.registry import Registry

#from ki.promptfactory.prompts.simpleprompt import SimplePrompt
#from ki.promptfactory.prompts.contextprompt import ContextPrompt
#from ki.promptfactory.prompts.contextfreiprompt import ContextFreiPrompt

from ki.promptfactory.prompts.simpleprompt import SimplePromptConfig
from ki.promptfactory.prompts.contextprompt import ContextPromptConfig
from ki.promptfactory.prompts.contextfreiprompt import ContextFreiPromptConfig


# %%
class HasPromptLlmConfig(Protocol):
    prompt: object
    llm_config: object

class PromptFactory:
    def __init__(self, registry: Registry, logger: logging.Logger):
        self.registry = registry
        self.logger = logger

    def build_prompt(self, config: HasPromptLlmConfig):
        """
        Baut eine Prompt-Komponente für eine HeadPromptLlm-Komponente.
        Nutzt Buildtime LLM-Config aus config.
        """
        prompt_type = config.prompt.prompt_type
        
        prompt_cls = self.registry.get(prompt_type)
        if not prompt_cls:
            if self.logger:
                self.logger.warning(
                    "Registry %s: Prompt '%s' nicht gefunden!",
                    type(self.registry).__name__,
                    prompt_type,
                )
            return None

        return prompt_cls(llm_config=config.llm_config)


# %%
PromptConfig = Union[SimplePromptConfig, ContextPromptConfig, ContextFreiPromptConfig]

# %%
