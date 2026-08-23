# libs/pipeline/registry.py
# In dieser Registry können die wrapper verschiedener pipelines registriert
# und über eine factory gebaut werden

import logging
from typing import Any, Type
from libs.pipeline.wrapper import BasePipelineWrapper

logger = logging.getLogger(__name__)


class PipelineRegistry:
    """
    Zentraler Service Locator für registrierte Pipeline-Wrapper.
    """

    def __init__(self) -> None:
        self._registry: dict[str, BasePipelineWrapper] = {}

    def bootstrap(self, pipeline_map: dict[str, Type[BasePipelineWrapper]]) -> None:
        """
        Instanziiert und registriert alle konfigurierten Wrapper-Klassen beim Anwendungsstart.
        """
        self._registry.clear()
        for pipeline_id, wrapper_cls in pipeline_map.items():
            instance = wrapper_cls()
            if instance.pipeline_id != pipeline_id:
                logger.warning(
                    "Mismatch zwischen Map-Key '%s' und wrapper.pipeline_id '%s'. Key wird verwendet.",
                    pipeline_id,
                    instance.pipeline_id,
                )
            self._registry[pipeline_id] = instance
            logger.info("📦 Pipeline registriert: '%s' [%s]", pipeline_id, wrapper_cls.__name__)

    def get(self, pipeline_id: str) -> BasePipelineWrapper:
        if pipeline_id not in self._registry:
            raise KeyError(f"Pipeline '{pipeline_id}' ist nicht in der Registry vorhanden.")
        return self._registry[pipeline_id]

    def list_pipelines(self) -> list[dict[str, Any]]:
        return [
            {
                "pipeline_id": wrapper.pipeline_id,
                "mode": wrapper.mode,
            }
            for wrapper in self._registry.values()
        ]


# Globale Single-Source Instanz
registry = PipelineRegistry()
