# libs/streampipe/single_runner.py
"""
Dieser Runner fürhrt eine StreamPipe Pipeline im Single Run Modus aus.
Dieser Runner kann genutzt werden um eine api bridge zu bauen, mit der
in microservice/pipeline-server automatisch ein FastAPI Endpunkt gebaut wird
"""
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from libs.streampipe.step import PipelineStep
from libs.streampipe.basemodels import BasePipelineEnv

class SinglePipelineRunner:
    """
    Punkt 4: Ein absolut generischer Single-Request-Runner.
    Er vollstreckt linear, ordnet Overrides auf Framework-Ebene generisch
    den Pydantic-Configs der Steps zu und liefert den Speicherpool.
    """
    def __init__(self, steps: List[PipelineStep], env: BasePipelineEnv, initial_input_class: type[BaseModel]):
        self.steps = steps
        self.env = env
        self.initial_input_class = initial_input_class

        # Punkt 2: Dynamisches Client-Mapping über das ENV ohne Fachwissen
        self.clients_dict = {
            "docling_client": getattr(self.env, "docling_client", None),
            "vllm_client": getattr(self.env, "vllm_client", None),
            "infinity_client": getattr(self.env, "infinity_client", None),
            "qdrant_service": getattr(self.env, "qdrant_client", None),
            "storage_client": getattr(self.env, "storage_client", None)
        }

    async def run(self, initial_payload: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> Dict[str, BaseModel]:
        """
        Führt einen einzelnen Durchlauf aus.
        overrides erwartet eine Struktur wie: {'StepName': {'param': wert}}
        """
        run_id = f"single_{uuid.uuid4().hex[:8]}"
        global_payload = initial_payload.copy()
        step_overrides = overrides or {}

        # Speicherpool für alle typisierten Ergebnis-Objekte
        history_pool: Dict[str, BaseModel] = {}

        # Initialen Input dynamisch bauen (z. B. QueryInput)
        current_data = self.initial_input_class(**initial_payload)

        for step in self.steps:
            # =====================================================================
            # ÄNDERUNG: Zentrales Mergen auf Instanzebene (base_config)
            # =====================================================================
            if step.name in step_overrides:
                specific_override = step_overrides[step.name]

                # Wir mutieren direkt die base_config des Steps vor dessen Ausführung
                if hasattr(step, "base_config") and isinstance(step.base_config, BaseModel):
                    try:
                        step.base_config = step.base_config.model_copy(update=specific_override)
                        print(f"🎯 Runner injected override directly into base_config for: {step.name}")
                    except Exception as e:
                        print(f"⚠️ Failed to apply centralized override for '{step.name}': {e}")
            # =====================================================================

            # ToDo: preprocess hook fehlt!
            
            # Reiner, unverfälschter Framework-Aufruf
            current_data = await step.execute(
                input_data=current_data,
                global_payload=global_payload,
                clients=self.clients_dict
            )
             
            # Postprocess-Hook ausführen
            current_data = step.postprocess(run_id, current_data, global_payload)

            # Ergebnis im Pool ablegen
            history_pool[step.name] = current_data

            # Generischer Abbruch bei Fehlersignalen
            if getattr(current_data, "status", "success") in ("error", "failed"):
                raise RuntimeError(f"Generischer Runner-Abbruch: Fehler in Step '{step.name}'")

        return history_pool
