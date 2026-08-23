# applications/rag/pipelines/rag_request/api_bridge.py
from typing import Dict, Any
from pydantic import BaseModel
from applications.rag.pipelines.rag_request.models import QueryInput
from libs.streampipe.single_runner import SinglePipelineRunner
from applications.rag.pipelines.rag_request.environment import run_preparation
from applications.rag.pipelines.rag_request.topology import create_rag_pipeline_steps


def build_rag_topology() -> SinglePipelineRunner:
    """Baut die spezifische RAG-Topologie für den generischen Runner zusammen."""
    env = run_preparation()

    steps = create_rag_pipeline_steps()

    return SinglePipelineRunner(steps=steps, env=env, initial_input_class=QueryInput)


import logging
logger = logging.getLogger("pipeline.api_bridge")

def transform_pool_to_api_response(pool: Dict[str, BaseModel]) -> Dict[str, Any]:
    """
    Reicht den vollständigen Zustand aller 
    Pipeline-Schritte (inkl. aller Metadaten, Scores und Parents) als 
    strukturiertes JSON-Objekt an das SDK weiter.
    """
        
    steps_serialized = {}
    
    for step_name, model_instance in pool.items():
        if isinstance(model_instance, BaseModel):
            # Rekursive Umwandlung in ein Standard-Python-Wörterbuch
            step_dict = model_instance.model_dump()
            
            # -----------------------------------------------------------------
            # #todo: Entfernen sobald Schalter eingebaut
            # Bandbreiten-Optimierung für das Chainlit-Frontend:
            # Wir löschen die 1024-dimensionalen Floats aus dem Netzwerk-Payload,
            # da das UI niemals rohe Vektoren visualisieren muss.
            if "dense_vector" in step_dict:
                del step_dict["dense_vector"]
            
            # Bereinigung redundanter Extras (falls dort noch Kopien liegen)
            if "extras" in step_dict and isinstance(step_dict["extras"], dict):
                # Falls in den Extras nochmals Vektoren oder massive redundante
                # Logs liegen, können sie hier temporär entfernt werden.
                pass
            # -----------------------------------------------------------------
            
            steps_serialized[step_name] = step_dict
        else:
            steps_serialized[step_name] = {"error": "Invalid base model", "raw": str(model_instance)}
           
    return {
        "steps": steps_serialized
    }   
