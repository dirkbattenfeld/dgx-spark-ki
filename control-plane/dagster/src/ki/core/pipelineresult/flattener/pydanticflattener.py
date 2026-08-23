# ki/core/pipelineresults/flattener/pydanticflattener.py

from ki.core.pipelineresult.flattener.registry import flattener_registry

from typing import Any, Optional
import logging
from datetime import datetime, date

@flattener_registry.register("standard")
class PydanticFlattener:
    def __init__(self, logger: Optional[logging.Logger] = None, sep: str = "."):
        self.logger = logger or logging.getLogger(__name__)
        self.sep = sep
        # Diese Keys alleine reichen nicht aus, um ein Objekt zu behalten
        self.technical_keys = {"component_id", "run_id", "executor_status"}

    def flatten(self, obj: Any) -> Any:
        """Der Einstiegspunkt, den dein Persistor aufruft."""
        # 1. In Basis-Typen wandeln (Pydantic -> Dict/List)
        if hasattr(obj, "model_dump"):
            data = obj.model_dump()
        elif hasattr(obj, "dict"):
            data = obj.dict()
        else:
            data = obj

        # 2. Rekursive Bereinigung und Flachklopfen starten
        return self._process_recursive(data)

    def _is_empty(self, v: Any) -> bool:
        """Prüft auf None, leere Container oder rein technische Container."""
        if v is None:
            return True
        if isinstance(v, (dict, list, str)) and len(v) == 0:
            return True
        
        # Spezialfall: Ein Dict, das nur technische Keys enthält
        if isinstance(v, dict):
            # Wir prüfen, ob alle Keys (nach dem Separator) technisch sind
            if v and all(k.split(self.sep)[-1] in self.technical_keys for k in v.keys()):
                return True
                
        return False

    def _process_recursive(self, d: Any, parent_key: str = "") -> Any:
        # FALL 1: Dictionary
        if isinstance(d, dict):
            flat_dict = {}
            for k, v in d.items():
                new_key = f"{parent_key}{self.sep}{k}" if parent_key else k
                res = self._process_recursive(v, new_key)
                
                if self._is_empty(res):
                    continue

                if isinstance(res, dict) and not self._is_complex_object(v):
                    flat_dict.update(res)
                else:
                    flat_dict[new_key] = res
            
            return flat_dict if not self._is_empty(flat_dict) else {}

        # FALL 2: Liste
        elif isinstance(d, list):
            cleaned_list = []
            for item in d:
                res = self._process_recursive(item)
                if not self._is_empty(res):
                    cleaned_list.append(res)
            return cleaned_list

        # FALL 3: Primitiver Wert
        else:
            if isinstance(d, (datetime, date)):
                return d.isoformat()
            return d

    def _is_complex_object(self, v: Any) -> bool:
        return not isinstance(v, (dict, list))
