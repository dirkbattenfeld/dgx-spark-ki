# libs/pipeline/steps.py

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Type
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PipelineStep:
    """
    Repräsentiert einen generischen Pipeline-Schritt.
    Unterstützt den vollen Lifecycle: preprocess -> execute -> postprocess.
    """
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
        """Preprocess-Hook vor der Ausführung des Steps."""
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
            
        # 1. Startzustand: Übergebener Override oder Standard-Konfiguration
        final_config = config_override or self.base_config
        overrides = None
        
        # 2. Der Adapter filtert NUR die Daten und extrahiert das flache Override-Wörterbuch
        if self._step_preparation:
            input_data, overrides = self._step_preparation(input_data, global_payload)
        
        # 3. Mergen dynamischer Step-Internal Overrides
        if overrides:
            final_config = final_config.model_copy(update=overrides)
        
        # Filtering der Clients für die Action
        sig = inspect.signature(self._step_action)
        action_params = sig.parameters.keys()
        
        filtered_clients = {
            k: v for k, v in clients.items() if k in action_params
        }
        
        # 4. Aufruf der reinen Action
        return await self._step_action(input_data, config=final_config, **filtered_clients)
    
    def postprocess(self, run_id: str, data: Any, global_payload: Dict[str, Any]) -> Any:
        """Postprocess-Hook nach der Ausführung des Steps."""
        if self._step_postprocess:
            return self._step_postprocess(run_id, data, global_payload)
        return data
    