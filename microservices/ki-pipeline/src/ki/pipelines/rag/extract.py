import logging
import httpx
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from typing import Any, Dict
from dataclasses import dataclass

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.rag.pdfloader import ExtractInput

class DoclingExtractConfig(BaseModel):
    timeout: float = 300.0  # Großzügiges Timeout für schwere PDFs

class RawDocument(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    markdown_content: str
    json_path: Path 
    metadata: Dict[str, Any]

@dataclass
class DoclingExtractRunContext(BaseRunContext[DoclingExtractConfig]):
    component_name: str
    config: DoclingExtractConfig
   
    def __post_init__(self):
        super().__init__(component_name=self.component_name, config=self.config)

@component_registry.register('extract_docling')
class ExtractDocling(BaseComponent):
    CONFIG_CLASS = DoclingExtractConfig
    INPUT_CLASS = ExtractInput
    OUTPUT_CLASS = RawDocument
    RUN_CONTEXT_CLASS = DoclingExtractRunContext

    def run(self, data: ExtractInput, *, component_ctx: DoclingExtractRunContext, global_ctx: GlobalRunContext) -> RawDocument:
        run_logger = global_ctx.run_logger
        cfg = component_ctx.config
        source_pdf = Path(data.source_pdf).absolute()
        
        run_logger.info(f"Sende Extraktions-Request für {source_pdf} an Docling-Service unter {global_ctx.infra.docling_url}.")

        # HTTP-Aufruf an den Microservice
        try:
            # Wir nutzen den synchronen Client für den linearen Ablauf in der Komponente
            with httpx.Client(base_url=global_ctx.infra.docling_url, timeout=cfg.timeout) as client:
                response = client.post(
                    "/extract", 
                    json={"source_pdf": str(source_pdf)}
                )
                
                # Fehler werfen, wenn der Service 4xx oder 5xx antwortet
                response.raise_for_status()
                
                result_data = response.json()
                
                run_logger.info(f"Extraktion erfolgreich abgeschlossen für {source_pdf}.")

                # Wir extrahieren die Daten aus dem API-Response
                markdown_content = result_data.get("markdown", "")
                json_path_str = result_data.get("json_path")
                status = result_data.get("status")

                output = RawDocument(
                    source_path=source_pdf, 
                    markdown_content=markdown_content,
                    json_path=Path(json_path_str) if json_path_str else None,
                    metadata={
                        "service_status": status,
                        "extraction_method": "docling_microservice"
                    }
                )
                return output

        except httpx.HTTPStatusError as e:
            run_logger.error(f"Docling Service Fehler ({e.response.status_code}): {e.response.text}")
            raise
        except Exception as e:
            run_logger.error(f"Unerwarteter Fehler bei der Kommunikation mit dem Docling Service: {str(e)}")
            raise
