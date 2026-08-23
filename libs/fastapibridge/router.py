# libs/fastapibridge/router.py

from typing import Any, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from libs.pipeline.registry import registry

router = APIRouter(prefix="/api/v1/pipelines", tags=["Pipelines"])


class PipelineRunRequest(BaseModel):
    pipeline_id: str = Field(..., description="ID der auszuführenden Pipeline")    
    payload: Optional[Any] = Field(
        default=None, description="Initial-Payloads für Input-Klasse / Prae-Pipeline Hook und optionale Config-Overrides"
    )
    overrides: Optional[dict[str, Any]] = Field(
        default=None, description="Optionale Config- oder Step-Overrides für den Run"
    )

class PipelineRunResponse(BaseModel):
    status: str
    pipeline_id: str
    data: Any


@router.get("/", status_code=status.HTTP_200_OK)
async def list_available_pipelines() -> dict[str, Any]:
    """
    Gibt die Liste aller registrierten Pipelines zurück (für Chainlit-UI-Auswahlmenüs).
    """
    return {"pipelines": registry.list_pipelines()}


@router.post("/run", response_model=PipelineRunResponse, status_code=status.HTTP_200_OK)
async def run_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
    """
    Führt eine registrierte Pipeline synchron über ihren Wrapper aus.
    """
    try:
        wrapper = registry.get(request.pipeline_id)

        result = await wrapper.execute(
            incoming_payload=request.payload,
            overrides=request.overrides
        )

        return PipelineRunResponse(
            status="success",
            pipeline_id=request.pipeline_id,
            data=result,
        )

    except KeyError as ke:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ke),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler bei der Pipeline-Ausführung: {str(e)}",
        )
