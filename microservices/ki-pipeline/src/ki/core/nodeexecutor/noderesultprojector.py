from typing import Any, Dict, List, Union, Optional

class NodeResultProjector:
    """
    Stufe 2: Konsolidiert PipelineResults fachlich.
    Agnostisch gegenüber Dagster. Erzeugt flache Dicts aus Pydantic-Modellen.
    """
    def __init__(self, sep: str = "/", blacklist: List[str] = None):
        self.sep = sep
        self.blacklist = blacklist or ["run_id", "write_artifact"]
    
    def _is_relevant_result(self, comp_res: Any) -> bool:
        """
        Prüft, ob das Komponentenergebnis fachlichen Inhalt hat.
        """
        # Wir prüfen, ob fachliche Summaries vorhanden und nicht leer sind
        has_outputs = bool(getattr(comp_res, "outputs_summary", {}))
        has_config = bool(getattr(comp_res, "config_summary", {}))
        
        # Optional: Prüfen, ob im runcontext_summary mehr als nur die run_id steht
        ctx = getattr(comp_res, "runcontext_summary", {})
        has_context_payload = len([k for k in ctx.keys() if k != "run_id"]) > 0

        return has_outputs or has_config or has_context_payload
    

    def _filter_components(self, pipeline_result: Any) -> Optional[Any]:
        """
        Erstellt eine Kopie des PipelineResult, die nur relevante Komponenten enthält.
        """
        if not pipeline_result:
            return None
            
        relevant_components = [
            c for c in pipeline_result.component_results 
            if self._is_relevant_result(c)
        ]
        
        if not relevant_components:
            return None
            
        # Wir geben ein neues Objekt zurück (oder manipulieren vorsichtig die Kopie)
        # Damit die raw_results im NodeExecutor unberührt bleiben:
        import copy
        new_res = copy.copy(pipeline_result)
        new_res.component_results = relevant_components
        return new_res


    def project(self, data: Union[Any, List[Any]]) -> Dict[str, Any]:
        """Verarbeitet PipelineResults und filtert leere Komponenten aus."""
        if isinstance(data, list):
            results = {}
            for i, item in enumerate(data):
                trial_key = f"trial_{i:03d}"
                # Hier filtern wir die Liste der Komponenten innerhalb eines Trials
                filtered_item = self._filter_components(item)
                if filtered_item: # Nur hinzufügen, wenn der Trial nicht komplett leer ist
                    results.update(self._flatten(filtered_item, trial_key))
            return results
        
        filtered_data = self._filter_components(data)
        return self._flatten(filtered_data)


    def _flatten(self, obj: Any, prefix: str = "") -> Dict[str, Any]:
        """Rekursives Flattening von Pydantic-Modellen und Dicts."""
        items = {}

        # 1. Konvertierung in Dictionary
        if hasattr(obj, "model_dump"):
            data = obj.model_dump()
        elif hasattr(obj, "__dict__") and not isinstance(obj, (str, dict, list)):
            data = vars(obj)
        else:
            data = obj

        # 2. Rekursives Durchlaufen
        if isinstance(data, dict):
            for k, v in data.items():
                new_key = f"{prefix}{self.sep}{k}" if prefix else k
                items.update(self._flatten(v, new_key))
        elif isinstance(data, list):
            for i, v in enumerate(data):
                # Sonderfall: ArtifactRefs haben eine URI
                if isinstance(v, dict) and "uri" in v:
                    items[f"{prefix}{self.sep}{i}{self.sep}uri"] = v["uri"]
                else:
                    items.update(self._flatten(v, f"{prefix}{self.sep}{i}"))
        else:
            # Endknoten (Basiswert)
            if data is not None:
                items[prefix] = data

        if isinstance(data, dict):
            for k, v in data.items():
                # Hier greift die Blacklist:
                if k in self.blacklist:
                    continue
                new_key = f"{prefix}{self.sep}{k}" if prefix else k
                items.update(self._flatten(v, new_key))

        return items
