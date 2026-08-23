# libs/pipeline/step.py

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Type
from pydantic import BaseModel

from libs.observability.wrapper import trace_step, trace_data

logger = logging.getLogger(__name__)


class PipelineStep:
    def __init__(
        self, 
        name: str,
        step_action: Callable[..., Any], 
        input_class: Type[BaseModel],
        config: BaseModel,
        step_preprocess: Optional[Callable[[str, Any, Dict[str, Any]], Any]] = None,
        step_preparation: Optional[Callable[[Any, Dict[str, Any]], tuple[Any, Optional[Dict[str, Any]]]]] = None,
        step_postprocess: Optional[Callable[[str, Any, Dict[str, Any]], Any]] = None
    ):
        self.name = name
        self.input_class = input_class
        self._step_action = step_action
        self._step_preprocess = step_preprocess
        self._step_preparation = step_preparation
        self._step_postprocess = step_postprocess
        self.base_config = config

    def preprocess(self, run_id: str, data: Any, global_payload: Dict[str, Any]) -> Any:
        if self._step_preprocess:
            return self._step_preprocess(run_id, data, global_payload)
        return data

    async def execute(
        self, 
        input_data: Any, 
        global_payload: Dict[str, Any], 
        clients: Dict[str, Any],
        config_override: Optional[BaseModel] = None
    ) -> Any:
        if not isinstance(input_data, self.input_class):
            input_data = self.input_class.model_validate(input_data)
            
        final_config = config_override or self.base_config
        overrides = None
        
        if self._step_preparation:
            input_data, overrides = self._step_preparation(input_data, global_payload)
        
        if overrides:
            final_config = final_config.model_copy(update=overrides)
        
        sig = inspect.signature(self._step_action)
        action_params = sig.parameters.keys()
        
        # Dynamisches Filtern der Clients und optionaler Parameter je nach Signatur
        action_kwargs = {}
        for k, v in clients.items():
            if k in action_params:
                action_kwargs[k] = v
                
        if "config" in action_params:
            action_kwargs["config"] = final_config
            
        if "global_payload" in action_params:
            action_kwargs["global_payload"] = global_payload
            
        # OTEL-Wrapper für Performance und Data-Payloads
        @trace_step(self.name)
        @trace_data(f"{self.name}.payload")
        async def _execute_wrapped(data_arg):
            if inspect.iscoroutinefunction(self._step_action):
                return await self._step_action(data_arg, **action_kwargs)
            else:
                return self._step_action(data_arg, **action_kwargs)

        return await _execute_wrapped(input_data)
    
    def postprocess(self, run_id: str, data: Any, global_payload: Dict[str, Any]) -> Any:
        if self._step_postprocess:
            return self._step_postprocess(run_id, data, global_payload)
        return data