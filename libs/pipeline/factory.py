# libs/pipeline/factory.py

from typing import Literal
from pydantic import BaseModel

from libs.pipeline.base import BasePipeline
from libs.pipeline.runner import (
    BasePipelineRunner, 
    SinglePipelineRunner, 
    StreamingPipelineRunner
)

class PipelineRunnerFactory:
    """
    Factory-Klasse zur Erstellung von Pipeline-Runnern aus einer Pipeline-Definition.
    Übernimmt den Aufbau von Environment, Steps und injiziert sie in den Runner.
    """
    @staticmethod
    def create_from_pipeline(
        pipeline: BasePipeline,
        config: BaseModel,
        mode: Literal["single", "streaming"] = "streaming"
    ) -> BasePipelineRunner:
        
        # 1. Environment und Steps über das Pipeline-Manifest erzeugen
        env = pipeline.create_environment(config)
        steps = pipeline.build_steps(config)
        initial_input_class = pipeline.initial_input_class
        
        # 2. Den passenden Runner instanziieren und zurückgeben
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
