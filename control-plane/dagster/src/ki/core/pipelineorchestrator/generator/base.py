# ki/core/pipelineorchestrator/base.py

import logging
from typing import Dict, Any, Generator, List
from abc import ABC, abstractmethod

from ki.core.pipelineorchestrator.generator.registry import generator_registry

RunOverrides = Dict[str, Dict[str, Any]]


class BaseRunGenerator(ABC):
    """
    Gemeinsames Interface für alle Run-Generatoren.
    """
    ExpectsFeedback: bool = False  # default: kein Feedback per send
    
    def process_feedback(self, result: Any) -> Any:
        return None
      
    @classmethod
    @abstractmethod
    def from_config(cls, config: Dict[str, Any], logger: logging.Logger) -> "BaseRunGenerator":
        """
        Erzeugt eine Generator-Instanz aus einer YAML-Config.
        """
        raise NotImplementedError

    @abstractmethod
    def generate(self) -> Generator[RunOverrides, None, None]:
        """
        Liefert pro Iteration genau ein RunOverrides-Dict.
        """
        raise NotImplementedError

    def __iter__(self):
        return self.generate()



@generator_registry.register("none")
class RunGeneratorNone(BaseRunGenerator):
    """
    Erzeugt genau einen Run mit leeren Overrides.
    """
    ExpectsFeedback: bool = False
    
    @classmethod
    def from_config(cls, config: Dict[str, Any], logger: logging.Logger) -> "RunGeneratorNone":
        return cls()

    def generate(self) -> Generator[RunOverrides, None, None]:
        yield {}


@generator_registry.register("list")
class RunGeneratorList(BaseRunGenerator):
    """
    Erzeugt Runs auf Basis einer Liste von Overrides.
    """
    ExpectsFeedback: bool = False
    
    def __init__(self, overrides_list: List[RunOverrides], logger: logging.Logger):
        self.overrides_list = overrides_list

    @classmethod
    def from_config(cls, config: Dict[str, Any], logger: logging.Logger) -> "RunGeneratorList":
        return cls(config)

    def generate(self) -> Generator[RunOverrides, None, None]:
        for overrides in self.overrides_list:
            yield overrides


@generator_registry.register("batch")
class RunGeneratorBatch(BaseRunGenerator):
    """
    Erzeugt mehrere Batches von Overrides basierend auf start, batch_size und batch_count.
    """
    ExpectsFeedback: bool = False
    
    def __init__(self, start: int, batch_size: int, batch_count: int, logger: logging.Logger):
        self.start = start
        self.batch_size = batch_size
        self.batch_count = batch_count

    @classmethod
    def from_config(cls, config: Dict[str, Any], logger: logging.Logger) -> "RunGeneratorBatch":
        return cls(**config)

    def generate(self) -> Generator[RunOverrides, None, None]:
        for i in range(self.batch_count):
            s = self.start + i * self.batch_size
            e = s + self.batch_size - 1
            yield {"questionselector": {"start": s, "end": e}}


@generator_registry.register("repeat")
class RunGeneratorRepeat(BaseRunGenerator):
    """
    Führt #repeats runs durch ohne Overrides
    """
    ExpectsFeedback: bool = False
    
    def __init__(self, repeats: int, logger: logging.Logger):
        self.repeats = repeats
        
    @classmethod
    def from_config(cls, config: Dict[str, Any], logger: logging.Logger) -> "RunGeneratorRepeat":
        return cls(**config)

    def generate(self) -> Generator[RunOverrides, None, None]:
        for i in range(self.repeats):
            yield {}

