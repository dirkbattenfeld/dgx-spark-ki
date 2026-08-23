# ki/core/datapipeline/runmetaprojector.py

from ki.core.datapipeline.datapipeline_dataclasses import ComponentRunMeta

import logging
from typing import Optional, List, Any, Dict
from pydantic import BaseModel


class ComponentRunMetaProjector:
    """
    Stufe 1: Projektion von Laufzeit-Objekten auf ComponentRunMeta.
    Verpackt alle Daten in ein Metadaten-Format mit Flags (drop, pipeline_output),
    damit nachfolgende Projektoren (Stufe 2) entscheiden können, was im 
    finalen PipelineResult landet.
    """

    # Attribute, die in der Pipeline eine technische Funktion haben, kommen in die Whitelist, 
    # damit sie sicher in die PipelineResults gelangen
    WHITELIST = ["override_node_configs"     # Overrides für NodeConfigs der downstream Nodes 
                 ]

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.whitelist = ComponentRunMetaProjector.WHITELIST

    def _is_inline_type(self, value: Any) -> bool:
        """Prüft, ob ein Wert klein genug für die persistente Meta-DB ist."""
        # 1. Primitive Typen sind immer okay
        if isinstance(value, (int, float, str, bool, type(None))):
            return True
        
        # 2. Komplexe Typen (Dicts, Listen, Pydantic, Dataclasses)
        # Wir wandeln sie gedanklich in einen String um oder prüfen die Länge
        try:
            if isinstance(value, (dict, list)):
                # Lockerung: 5000 Zeichen / 100 Elemente (reicht für fast jede Config)
                return len(str(value)) < 5000 and len(value) < 100
            
            # Pydantic-Modelle oder Dataclasses als inline erlauben
            if hasattr(value, "model_dump") or hasattr(value, "__dataclass_fields__"):
                return len(str(value)) < 5000
        except:
            return False
        
        return False
    
    def _extract_with_metadata(self, obj: Any, artifact_refs: Optional[List[Any]] = None) -> Dict[str, Any]:
        """
        Extrahiert Attribute eines Objekts und verpackt sie in ein einheitliches
        Metadaten-Dict inklusive der Steuerungs-Flags.
        """
        if obj is None:
            return {}

        summary = {}
        # Felder bestimmen: Pydantic vs. Standard-Objekte
        if isinstance(obj, BaseModel):
            iterable = obj.model_fields.keys()
        else:
            # vars(obj) für Dataclasses/normale Klassen, private Felder ignorieren
            iterable = [f for f in vars(obj).keys() if not f.startswith('_')]

        # Flags aus der Klassen-Definition lesen (statische Attribute)
        drop_list = getattr(type(obj), "_drop_outputs", [])
        pipeline_list = getattr(type(obj), "_pipeline_outputs", [])

        for attr_name in iterable:
            try:
                attr_value = getattr(obj, attr_name)
            except AttributeError:
                continue

            is_inline = self._is_inline_type(attr_value)
            
            # Artifact-Referenz suchen (hauptsächlich für Outputs relevant)
            artifact_ref = None
            if artifact_refs:
                for ar in artifact_refs:
                    if ar.attribute_name == attr_name:
                        artifact_ref = ar
                        break

            summary[attr_name] = {
                "value": attr_value if is_inline else None,
                "attribute_name": attr_name,
                "class_name": type(obj).__name__,
                "instance_name": id(obj),
                "inline": is_inline,
                "drop": attr_name in drop_list,
                # Attribute in Whitelist auf jeden Fall mit in die PipelineResults
                "pipeline_output": attr_name in pipeline_list or attr_name in self.whitelist,   
                "write_artifact": artifact_ref is not None,
                "artifact_ref": artifact_ref,
            }

        return summary

    def project(
        self,
        *,
        component_spec: Any, # ComponentSpec
        output: Any,
        run_ctx: Any,        # BaseRunContext
        global_ctx: Any,     # GlobalRunContext
        artifact_refs: List[Any], # List[ArtifactRef]
    ) -> Any: # Returns ComponentRunMeta
        """
        Erstellt die vollständige Metadaten-Zusammenfassung einer Komponente.
        """
        
        # 1. Output Summary (Inklusive Artifact-Mapping)
        outputs_summary = self._extract_with_metadata(output, artifact_refs)

        # 2. Config Summary (Extrahiert aus der build_config der Spec)
        # Wir extrahieren die Config der Komponente
        config_obj = getattr(component_spec, "build_config", component_spec)
        config_summary = self._extract_with_metadata(config_obj)

        # 3. RunContext Summary (Inklusive deiner markierten 'config')
        runcontext_summary = self._extract_with_metadata(run_ctx)
        
        # Manuelle Ergänzung von System-Metadaten, die immer verfügbar sein sollen
        runcontext_summary["run_id"] = {
            "value": getattr(global_ctx, "run_id", "unknown"),
            "attribute_name": "run_id",
            "pipeline_output": True, # Damit es im PipelineResult erscheint
            "inline": True,
            "drop": False
        }
        
        if hasattr(global_ctx, "run_path"):
            runcontext_summary["run_path"] = {
                "value": str(global_ctx.run_path),
                "attribute_name": "run_path",
                "pipeline_output": False, # Interner Pfad, meist nicht für Trial-Results
                "inline": True,
                "drop": False
            }

        # Rückgabe des fertigen Meta-Objekts
        # Hier wird angenommen, dass ComponentRunMeta diese Felder im Constructor akzeptiert
        return ComponentRunMeta(
            component_id=component_spec.name,
            config_summary=config_summary,
            runcontext_summary=runcontext_summary,
            outputs_summary=outputs_summary,
            artifacts=artifact_refs,
        )
