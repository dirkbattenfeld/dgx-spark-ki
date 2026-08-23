# libs/streampipe/steps.py

import inspect
from typing import Any, Callable, Dict, Optional, Type
from pydantic import BaseModel


class PipelineStep:
    """
    Repräsentiert einen generischen Pipeline-Schritt.
    Die execute-Methode agiert als automatische Config-Factory und filtert Clients.
    """
    def __init__(
        self, 
        name: str,
        step_action: Callable[..., Any], 
        input_class: Type[BaseModel],
        config: BaseModel,
        step_preparation: Optional[Callable[[Any, Dict[str, Any]], tuple[Any, Optional[Dict[str, Any]]]]] = None,
        step_postprocess: Optional[Callable[[str, Any, Dict[str, Any]], Any]] = None
    ):
        self.name = name
        self.input_class = input_class
        self._step_action = step_action
        self._step_preparation = step_preparation
        self._step_postprocess = step_postprocess
        self.base_config = config

    async def execute(self, input_data: Any, global_payload: Dict[str, Any], clients: Dict[str, Any]) -> Any:
        if not isinstance(input_data, self.input_class):
            input_data = self.input_class.model_validate(input_data)
            
        # 1. Startzustand: Standard-Konfiguration und optionale Overrides
        final_config = self.base_config
        overrides = None
        
        # 2. Der Adapter filtert NUR die Daten und extrahiert das flache Override-Wörterbuch
        if self._step_preparation:
            input_data, overrides = self._step_preparation(input_data, global_payload)
        
        # 3. DIE FACTORY-LOGIK: Das Framework mergt die Overrides absolut typsicher
        if overrides:
            final_config = self.base_config.model_copy(update=overrides)
        
        # Wir filtern das `clients`-Dict, sodass NUR Keys übergeben werden, die die Action auch wirklich erwartet.
        sig = inspect.signature(self._step_action)
        action_params = sig.parameters.keys()
        
        filtered_clients = {
            k: v for k, v in clients.items() if k in action_params
        }
        
        # 4. Aufruf der reinen Action mit der fertig generierten Config und den passenden Clients
        return await self._step_action(input_data, config=final_config, **filtered_clients)
    
    def postprocess(self, run_id: str, data: Any, global_payload: Dict[str, Any]) -> Any:
        if self._step_postprocess:
            return self._step_postprocess(run_id, data, global_payload)
        return data
