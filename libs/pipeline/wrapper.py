# libs/pipeline/wrapper.py

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set, Literal, Optional, Type
from pydantic import BaseModel

from libs.pipeline.base import BasePipeline
from libs.pipeline.factory import PipelineRunnerFactory
from libs.pipeline.runner import BasePipelineRunner

logger = logging.getLogger(__name__)


class BasePipelineWrapper(ABC):
    """
    Abstrakte Basisklasse (Template Method Pattern) für Pipeline-Wrapper.
    Orchestriert Observability, Runner-Erstellung über die Factory sowie Intro- und Outro-Hooks.
    Damit können Pipelines im Pipeline Framework in eine Registry gehängt und per Factory ausgeführt werden. 
    """

    @property
    @abstractmethod
    def pipeline_id(self) -> str:
        """Eindeutiger Identifier der Pipeline."""
        pass

    @property
    @abstractmethod
    def pipeline_class(self) -> Type[BasePipeline]:
        """Die Manifest-Klasse der Pipeline."""
        pass

    @property
    @abstractmethod
    def config_class(self) -> Type[BaseModel]:
        """Die Pydantic-Klasse der Gesamtkonfiguration."""
        pass

    @property
    def mode(self) -> Literal["single", "streaming"]:
        """Standard-Runner-Modus der Pipeline."""
        return "single"

    async def prepare_payloads(
        self,
        runner: BasePipelineRunner,
        config: BaseModel,
        incoming_payload: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """
        INTRO-HOOK: Bereitet die initialen Payloads vor.
        Kann in konkreten Wrappern überschrieben werden (z. B. für S3-Scans).
        """
        return incoming_payload if incoming_payload is not None else []

    # Post Pipeline Hook um die gesamten Pipeline Results zu verarbeiten
    # Hilfsfunktionen für: 
    #   Aggregation des Status über alle Steps
    #   Herausfiltern von keys aus den Results über eine Liste von Pfaden zu den keys
    
    @staticmethod
    def _get_by_path(data: Any, path: str) -> Any:
        """Navigiert durch Dicts und Listen via Punktnotation."""
        if data is None or not path:
            return None

        keys = path.split(".")
        curr = data

        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            elif isinstance(curr, list):
                if k.isdigit():
                    idx = int(k)
                    curr = curr[idx] if 0 <= idx < len(curr) else None
                else:
                    # Key-Suche in einer Liste von Dicts (sucht im ersten treffenden Dict)
                    found = None
                    for item in curr:
                        item_dict = item.model_dump() if hasattr(item, "model_dump") else (
                            item.dict() if hasattr(item, "dict") else (
                                item if isinstance(item, dict) else {}
                            )
                        )
                        if k in item_dict:
                            found = item_dict[k]
                            break
                    curr = found
            else:
                return None

        return curr


    def filter_paths(
        self,
        data: Any,
        exclude_paths: Set[str],
    ) -> Any:
        """Entfernt gezielt spezifische Pfade iterativ aus Dicts oder Listen."""
        if not exclude_paths or data is None:
            return data

        for path in exclude_paths:
            keys = path.split(".")

            # Falls Wurzel eine Liste ist, wenden wir das Matching auf jedes Element an
            root_items = data if isinstance(data, list) else [data]

            for item in root_items:
                curr = item
                # Bis zum vorletzten Key navigieren
                for key in keys[:-1]:
                    if isinstance(curr, dict) and key in curr:
                        curr = curr[key]
                    elif isinstance(curr, list) and key.isdigit():
                        idx = int(key)
                        curr = curr[idx] if 0 <= idx < len(curr) else None
                    else:
                        curr = None
                        break

                # Ziel löschen
                if isinstance(curr, dict) and keys[-1] in curr:
                    curr.pop(keys[-1], None)

        return data


    def aggregate_status(self, statuses: List[str]) -> str:
        """Binäre Status-Aggregation: 'success' nur wenn alle 'success' sind."""
        if not statuses:
            return "unknown"
        return "success" if all(s == "success" for s in statuses) else "failed"

    
    def aggregate_statuses_from_paths(
        self, data: Any, status_paths: List[str]
    ) -> Dict[str, Any]:
        """
        Extrahiert Statuswerte aus Pfaden, aggregiert sie binär und liefert
        eine detaillierte Übersicht aller Einzelstatus zurück.
        """
        step_details: Dict[str, str] = {}
        raw_statuses: List[str] = []

        for path in status_paths:
            val = self._get_by_path(data, path)
            status_str = str(val) if val is not None else "failed"
            
            # Nutzen des letzten Pfad-Segments oder des Pfades als Key für Transparenz
            step_details[path] = status_str
            raw_statuses.append(status_str)

        # Binäre Aggregation über den Hilfsmethode
        global_status = self.aggregate_status(raw_statuses)

        return {
            "status": global_status,
            "steps": step_details,
        }
    
    
    # Post Pipeline Hook    
    async def process_results(
        self,
        raw_results: list[Any],
        config: BaseModel,
    ) -> Any:
        """
        OUTRO-HOOK: Aggregiert oder formatiert die Pipeline-Ergebnisse für den Aufrufer.
        """
        return raw_results

    #
    # Ausführung des Wrappers
    #    
    
    async def execute(
        self,
        incoming_payload: Optional[list[dict[str, Any]]] = None,
        overrides: Optional[dict[str, Any]] = None
    ) -> Any:
        """
        Zentraler Ausführungs-Workflow.
        """
        # 1. Konfiguration & Manifest instanziieren
        config = self.config_class()
        pipeline_def = self.pipeline_class()
        mode = self.mode       

        # 3. Runner über Factory bauen
        runner = PipelineRunnerFactory.create_from_pipeline(
            pipeline=pipeline_def,
            config=config,
            mode=mode,
        )

        logger.info("=" * 60)
        logger.info("🚀 EXECUTE PIPELINE: %s (Modus: %s)", self.pipeline_id, mode)
        logger.info("=" * 60)

        # 4. INTRO-HOOK aufrufen
        payloads = await self.prepare_payloads(
            runner=runner,
            config=config,
            incoming_payload=incoming_payload,
        )

        if not payloads:
            logger.warning("⚠️ Keine Payloads für Pipeline '%s' bereitgestellt. Abbruch.", self.pipeline_id)
            return await self.process_results([], config)

        logger.info("🎯 %d Payloads für Execution bereitgestellt. Starte Runner...", len(payloads))

        # 5. Pipeline ausführen
        raw_results = await runner.run(
            initial_payloads=payloads,
            overrides=overrides
        )

        logger.info("✅ Execution beendet. %d Ergebnisse empfangen.", len(raw_results))

        # 6. OUTRO-HOOK aufrufen
        return await self.process_results(raw_results, config)
