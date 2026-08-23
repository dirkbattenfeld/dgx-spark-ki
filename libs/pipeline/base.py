# libs/pipeline/base.py

from abc import ABC, abstractmethod
from typing import List, Type, Literal
from pydantic import BaseModel

from libs.pipeline.basemodels import BasePipelineEnv
from libs.pipeline.step import PipelineStep


class BasePipeline(ABC):
    """
    Abstract Base Class für alle konkreten Pipeline-Definitionen.
    Kapselt den gesamten Lebenszyklus und die Komponenten einer Pipeline.
    """
    
    @property
    @abstractmethod
    def pipeline_id(self) -> str:
        """Eindeutiger Identifier für die Registry (z.B. 'rag_ingestion')."""
        pass

    @property
    @abstractmethod
    def config_class(self) -> Type[BaseModel]:
        """Die Pydantic-Klasse für die Gesamtkonfiguration."""
        pass

    @property
    @abstractmethod
    def initial_input_class(self) -> Type[BaseModel]:
        """Das Pydantic Input Model für das erste Element in der Pipeline."""
        pass

    @abstractmethod
    def create_environment(self, config: BaseModel) -> BasePipelineEnv:
        """Instanziiert die spezifische Ausführungsumgebung und schließt Ressourcen an."""
        pass

    @abstractmethod
    def build_steps(self, config: BaseModel) -> List[PipelineStep]:
        """Erzeugt die Liste der vorkonfigurierten PipelineSteps."""
        pass

    