# apps/api/router.py

from typing import Any, Dict, List, Literal, Optional, Union
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from libs.pipeline.factory import PipelineRunnerFactory
from libs.pipeline.basemodels import BasePipelineEnv
# Angenommener Import deines zentralen Envs / Dependency Injection
from apps.api.dependencies import get_pipeline_env, get_pipeline_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


# 1. Generisches Request-Schema
class PipelineExecutionRequest(BaseModel):
    pipeline_id: str = Field(..., description="Eindeutiger Bezeichner der registrierten Pipeline")
    mode: Literal["single", "streaming"] = Field("single", description="Ausführungsmodus")
    payload: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(
        ..., 
        description="Ein Dict für 'single' oder eine Liste von Dicts für 'streaming'"
    )
    overrides: Optional[Dict[str, Any]] = Field(
        None, 
        description="Optionale Step-Config Overrides: {'StepName': {'param': wert}}"
    )


# 2. Generischer Endpoint
@router.post("/run", response_model=Union[Dict[str, Any], List[Dict[str, Any]]])
async def run_pipeline(
    request: PipelineExecutionRequest,
    env: BasePipelineEnv = Depends(get_pipeline_env),
    registry: Dict[str, Any] = Depends(get_pipeline_registry)
):
    # A. Pipeline-Definition aus der Registry auflösen
    pipeline_def = registry.get(request.pipeline_id)
    if not pipeline_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{request.pipeline_id}' ist nicht in der Registry registriert."
        )

    steps = pipeline_def["steps"]
    initial_input_class = pipeline_def["initial_input_class"]

    # B. Payload-Typ-Validierung gegen den gewählten Modus
    if request.mode == "single" and not isinstance(request.payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Im Modus 'single' muss 'payload' ein Einzell-Dict sein."
        )
    if request.mode == "streaming" and not isinstance(request.payload, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Im Modus 'streaming' muss 'payload' eine Liste von Dicts sein."
        )

    # C. Runner via Factory instanziieren
    try:
        runner = PipelineRunnerFactory.create(
            mode=request.mode,
            steps=steps,
            env=env,
            initial_input_class=initial_input_class
        )
    except Exception as e:
        logger.error("Fehler bei Runner-Erstellung: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Runner konnte nicht erzeugt werden: {str(e)}"
        )

    # D. Ausführung & automatische Serialisierung der gefilterten Results
    try:
        results = await runner.run(
            initial_payload=request.payload,  # Reicht dict oder list[dict] durch
            overrides=request.overrides
        )
        return results

    except Exception as e:
        logger.error("Pipeline-Ausführung fehlgeschlagen: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kritischer Fehler bei der Pipeline-Ausführung: {str(e)}"
        )
