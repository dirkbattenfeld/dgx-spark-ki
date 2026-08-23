# libs/streampipe/runner.py

import asyncio
import logging
import uuid
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Type, Union
from pydantic import BaseModel

from libs.pipeline.basemodels import BasePipelineEnv
from libs.pipeline.step import PipelineStep

logger = logging.getLogger(__name__)


class BasePipelineRunner:
    def __init__(
        self, 
        steps: List[PipelineStep], 
        env: BasePipelineEnv,
        initial_input_class: Type[BaseModel]
    ):
        self.steps = steps
        self.env = env
        self.initial_input_class = initial_input_class

    @property
    def clients_dict(self) -> Dict[str, Any]:
        return self.env.get_clients()

    def _get_semaphore_context(self):
        semaphore = getattr(self.env, "doc_semaphore", None)
        if semaphore and isinstance(semaphore, asyncio.Semaphore):
            return semaphore
        return nullcontext()

    def _filter_for_history(self, data: Any) -> Any:
        if not isinstance(data, BaseModel):
            return data

        exclude_fields = set()
        drop_attrs = getattr(data, "_drop_outputs", None)
        if drop_attrs and isinstance(drop_attrs, (list, set, tuple)):
            exclude_fields.update(drop_attrs)

        return data.model_dump(exclude=exclude_fields if exclude_fields else None)

    async def _execute_single_run(
        self, 
        run_id: str, 
        global_payload: Dict[str, Any], 
        overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        
        step_overrides = overrides or {}
        history_pool: Dict[str, Any] = {}

        async with self._get_semaphore_context():
            logger.info("⚙️ Start Run [%s]", run_id)

            try:
                current_data = self.initial_input_class(**global_payload)
            except Exception as e:
                logger.error("💥 Fehler bei Instanziierung von %s für Run [%s]: %s", 
                             self.initial_input_class.__name__, run_id, e)
                return history_pool

            for step in self.steps:
                try:
                    step_config = step.base_config
                    if step.name in step_overrides and isinstance(step_config, BaseModel):
                        try:
                            step_config = step_config.model_copy(update=step_overrides[step.name])
                        except Exception as e:
                            logger.warning("⚠️ Failed to apply override for '%s': %s", step.name, e)

                    current_data = step.preprocess(run_id, current_data, global_payload)
                    
                    current_data = await step.execute(
                        input_data=current_data,
                        global_payload=global_payload,
                        clients=self.clients_dict,
                        config_override=step_config
                    )

                    current_data = step.postprocess(run_id, current_data, global_payload)
                    history_pool[step.name] = self._filter_for_history(current_data)

                    status = getattr(current_data, "status", "success")
                    if status in ("error", "failed"):
                        logger.warning("🛑 Abbruch der Pipeline [%s] bei Step '%s'.", run_id, step.name)
                        break

                except Exception as e:
                    logger.error("💥 Kritischer Fehler in Step '%s' für Run [%s]: %s", step.name, run_id, e)
                    break

        history_pool["_meta"] = {
            "run_id": run_id
        }
        return history_pool
 

class SinglePipelineRunner(BasePipelineRunner):
    """
    Takes one job as mapping or first job of a list of mappings
    """
    
    async def run(
        self, 
        initial_payloads: Union[List[Dict[str, Any]], Dict[str, Any]], 
        overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        
        run_id = f"single_{uuid.uuid4().hex[:8]}"
        
        if isinstance(initial_payloads, list):
            payload = initial_payloads[0]
        else:
            payload = initial_payloads
        
        return await self._execute_single_run(
            run_id=run_id, 
            global_payload=payload, 
            overrides=overrides
        )


class StreamingPipelineRunner(BasePipelineRunner):
    """
    Takes multiple jobs as a list of mappings
    Uses parallel job streaming through steps
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

        results = await asyncio.gather(*tasks, return_exceptions=True)

        cleaned_results: List[Dict[str, Any]] = []
        for res in results:
            if isinstance(res, Exception):
                logger.error("💥 Paralleler Task mit Exception abgebrochen: %s", res)
                cleaned_results.append({})
            else:
                cleaned_results.append(res)

        return cleaned_results
