# libs/streampipe/runner.py

import asyncio
import logging
import uuid
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel

from libs.streampipe.basemodels import BasePipelineEnv
from libs.streampipe.step import PipelineStep

logger = logging.getLogger(__name__)


class BasePipelineRunner:
    """
    Gemeinsame Basisklasse für Single- und Streaming-Pipeline-Runner.
    Kapselt Client-Mapping, Concurrency-Steuerung, Execution-Lifecycle
    und Ergebnis-Filterung.
    """
    def __init__(
        self, 
        steps: List[PipelineStep], 
        env: BasePipelineEnv,
        initial_input_class: Type[BaseModel]
    ):
        self.steps = steps
        self.env = env
        self.initial_input_class = initial_input_class

        # Dynamisches Client-Mapping aus dem ENV
        self.clients_dict = {
            "docling_client": getattr(self.env, "docling_client", None),
            "vllm_client": getattr(self.env, "vllm_client", None),
            "infinity_client": getattr(self.env, "infinity_client", None),
            "qdrant_service": getattr(self.env, "qdrant_client", None),
            "storage_client": getattr(self.env, "storage_client", None)
        }

    def _get_semaphore_context(self):
        """Liefert die Semaphore aus dem ENV oder einen NullContext als Fallback."""
        semaphore = getattr(self.env, "doc_semaphore", None)
        if semaphore and isinstance(semaphore, asyncio.Semaphore):
            return semaphore
        return nullcontext()

    def _filter_for_history(self, data: Any) -> Any:
        """
        Filtert Pydantic-Modelle für den history_pool.
        Berücksichtigt Field(exclude=True) sowie das _drop_outputs Attribut.
        """
        if not isinstance(data, BaseModel):
            return data

        exclude_fields = set()
        
        # 1. Private _drop_outputs aus BaseComponentResult auslesen
        drop_attrs = getattr(data, "_drop_outputs", None)
        if drop_attrs and isinstance(drop_attrs, (list, set, tuple)):
            exclude_fields.update(drop_attrs)

        # 2. Pydantic model_dump schließt automatisch Field(exclude=True)
        # und zusätzlich angegebene exclude_fields aus
        return data.model_dump(exclude=exclude_fields if exclude_fields else None)

    async def _execute_single_run(
        self, 
        run_id: str, 
        global_payload: Dict[str, Any], 
        overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Führt genau einen Durchlauf durch alle Pipeline-Schritte isoliert aus.
        """
        step_overrides = overrides or {}
        history_pool: Dict[str, Any] = {}

        async with self._get_semaphore_context():
            info_val = next(iter(global_payload.values())) if global_payload else "No Payload"
            logger.info("⚙️ Start Run [%s] (%s)", run_id, info_val)

            try:
                current_data = self.initial_input_class(**global_payload)
            except Exception as e:
                logger.error("💥 Fehler bei Instanziierung von %s für Run [%s]: %s", 
                             self.initial_input_class.__name__, run_id, e)
                return history_pool

            for step in self.steps:
                try:
                    # 1. Lokales Mergen von Config-Overrides (Verhindert Race Conditions)
                    step_config = step.base_config
                    if step.name in step_overrides and isinstance(step_config, BaseModel):
                        try:
                            step_config = step_config.model_copy(update=step_overrides[step.name])
                            logger.debug("🎯 Override injected into config for step: %s", step.name)
                        except Exception as e:
                            logger.warning("⚠️ Failed to apply override for '%s': %s", step.name, e)

                    # 2. Preprocess-Hook
                    current_data = step.preprocess(run_id, current_data, global_payload)

                    # 3. Step Execution
                    current_data = await step.execute(
                        input_data=current_data,
                        global_payload=global_payload,
                        clients=self.clients_dict,
                        config_override=step_config
                    )

                    # 4. Postprocess-Hook
                    current_data = step.postprocess(run_id, current_data, global_payload)

                    # 5. Speicherschonend gefiltertes Ergebnis im Pool ablegen
                    history_pool[step.name] = self._filter_for_history(current_data)

                    # Status-Prüfung
                    status = getattr(current_data, "status", "success")
                    if status in ("error", "failed"):
                        logger.warning("🛑 Abbruch der Pipeline [%s] bei Step '%s'.", run_id, step.name)
                        break

                except Exception as e:
                    logger.error("💥 Kritischer Fehler in Step '%s' für Run [%s]: %s", step.name, run_id, e)
                    break

        return history_pool


class SinglePipelineRunner(BasePipelineRunner):
    """
    Führt einen einzelnen Request/Payload synchronisiert durch die Pipeline aus.
    """
    async def run(
        self, 
        initial_payload: Dict[str, Any], 
        overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        run_id = f"single_{uuid.uuid4().hex[:8]}"
        return await self._execute_single_run(
            run_id=run_id, 
            global_payload=initial_payload, 
            overrides=overrides
        )


class StreamingPipelineRunner(BasePipelineRunner):
    """
    Führt mehrere Payloads parallel (Streaming/Batch) durch die Pipeline aus
    und sammelt alle Resultat-Pools.
    """
    async def run(
        self, 
        initial_payloads: List[Dict[str, Any]], 
        overrides: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        tasks = []
        for payload in initial_payloads:
            run_id = f"stream_{uuid.uuid4().hex[:8]}"
            tasks.append(
                self._execute_single_run(
                    run_id=run_id, 
                    global_payload=payload, 
                    overrides=overrides
                )
            )

        # Alle Streams parallel ausführen und Ergebnisse als Liste sammeln
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Abfangen von unerwarteten Task-Exceptions
        cleaned_results: List[Dict[str, Any]] = []
        for res in results:
            if isinstance(res, Exception):
                logger.error("💥 Paralleler Task mit Exception abgebrochen: %s", res)
                cleaned_results.append({})
            else:
                cleaned_results.append(res)

        return cleaned_results
