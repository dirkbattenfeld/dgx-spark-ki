# libs/pipeline/factory.py

from typing import List, Type, Literal
from pydantic import BaseModel

from libs.pipeline.basemodels import BasePipelineEnv
from libs.pipeline.step import PipelineStep
from libs.pipeline.runner import (
    BasePipelineRunner, 
    SinglePipelineRunner, 
    StreamingPipelineRunner
)

class PipelineRunnerFactory:
    """
    Factory-Klasse zur Erstellung von Pipeline-Runnern im 'single'- oder 'streaming'-Modus.
    """
    @staticmethod
    def create(
        mode: Literal["single", "streaming"],
        steps: List[PipelineStep],
        env: BasePipelineEnv,
        initial_input_class: Type[BaseModel]
    ) -> BasePipelineRunner:
        
        if mode == "single":
            return SinglePipelineRunner(
                steps=steps, 
                env=env, 
                initial_input_class=initial_input_class
            )
        elif mode == "streaming":
            return StreamingPipelineRunner(
                steps=steps, 
                env=env, 
                initial_input_class=initial_input_class
            )
        else:
            raise ValueError(f"Unbekannter Runner-Modus: '{mode}'. Erlaubt sind 'single' und 'streaming'.")
