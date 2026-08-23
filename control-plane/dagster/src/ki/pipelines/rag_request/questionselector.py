from dataclasses import dataclass
from typing import ClassVar
from pydantic import BaseModel, ConfigDict

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult

class QueryInput(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    query: str
#    top_n: int = 20
#    top_n1: int = 5
    _pipeline_outputs: ClassVar[list[str]] = ['query', 'top_n', 'top_n1']

class QuestionSelectorConfig(BaseModel):
    # Der Standard-Prompt, der in der YAML definiert wird
    user_query: str = "Welche THG Emissionen werden für 2024 genannt?"
#    top_n: int = 20
#    top_n1: int = 5

@dataclass
class QuestionSelectorRunContext(BaseRunContext[QuestionSelectorConfig]):
    component_name: str
    config: QuestionSelectorConfig

@component_registry.register("question_selector")
class QuestionSelector(BaseComponent):
    """
    Entry-Point Komponente. 
    INPUT_CLASS ist None, da sie als Initialzünder der Pipeline fungiert.
    Erzeugt das QueryInput-Objekt für die nachfolgende Retrieval-Kette.
    """
    CONFIG_CLASS: ClassVar[type] = QuestionSelectorConfig
    INPUT_CLASS: ClassVar[None] = None  # Explizit als Loader/Starter markiert
    OUTPUT_CLASS: ClassVar[type] = QueryInput
    RUN_CONTEXT_CLASS: ClassVar[type] = QuestionSelectorRunContext

    def run(
        self, 
        data: None, 
        *, 
        component_ctx: QuestionSelectorRunContext, 
        global_ctx: GlobalRunContext
    ) -> QueryInput:
        run_logger = global_ctx.run_logger
        cfg = component_ctx.config

        run_logger.info(f"QuestionSelector aktiviert. Nutze Query: '{cfg.user_query}'")

        # Erstellung des Objekts, das von EmbedQuery erwartet wird
        results = QueryInput(
            query=cfg.user_query
        )

        return results
