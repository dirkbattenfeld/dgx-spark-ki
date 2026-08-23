import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

# Imports aus dem Ziel-Framework
from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, BaseRunContext
from ki.pipelines.base.base import BaseComponent
from ki.pipelines.base.registry import component_registry

# 🌟 DEINE NEUEN FACHLOGIK-IMPORTS (Präzise nach deiner Vorgabe)
from libs.ki_dgxsdk.ki_sdk import DGX_Client
from applications.rag.pipelines.rag_ingestion.steps.configs import ExtractConfig
from applications.rag.pipelines.rag_ingestion.steps.models import ExtractInput, RawDocument
from applications.rag.pipelines.rag_ingestion.steps.extract import (
    extract_action,
    extract_prepare,
)


# 1. Configuration Class (Direkt gekoppelt an deine Fach-Config)
class DoclingExtractConfig(ExtractConfig):
    """
    Erbt direkt von deiner Fach-ExtractConfig, damit alle Parameter
    (detailed_tables, ocr_enabled, etc.) im Ziel-Framework verfügbar sind.
    """
    pass


# 2. Run Context Class
@dataclass
class DoclingExtractRunContext(BaseRunContext[DoclingExtractConfig]):
    component_name: str
    config: DoclingExtractConfig

    def __post_init__(self):
        super().__init__(component_name=self.component_name, config=self.config)


# 3. Die registrierte Pipeline-Komponente
@component_registry.register('extract_docling')
class ExtractDocling(BaseComponent):
    # Das strikt geforderte Klassen-Interface des Ziel-Frameworks
    CONFIG_CLASS = DoclingExtractConfig
    INPUT_CLASS = ExtractInput
    OUTPUT_CLASS = RawDocument
    RUN_CONTEXT_CLASS = DoclingExtractRunContext

    def run(self, data: ExtractInput, *, component_ctx: DoclingExtractRunContext, global_ctx: GlobalRunContext) -> RawDocument:
        run_logger = global_ctx.run_logger
        cfg = component_ctx.config
        
        sdk = DGX_Client(
            config_path="/app/microservices.yaml", 
            use_dispatcher=False)
        
        docling_client = sdk.get_client("docling")

        run_logger.info(f"🛫 [Extract] Starte Verarbeitung für S3-Pfad: {data.source_path}")

        # 1. In-Memory Kontext für die Fachlogik-Hooks vorbereiten
        # (Zieht z. B. den docling_json_path an)
        step_context = {}
        step_context = extract_prepare(data.source_path, step_context)

        # 3. Asynchronen Aufruf in den synchronen Ablauf des Frameworks einbetten
        try:
            output_document = asyncio.run(
                extract_action(
                    input_data=data,
                    context=step_context,
                    docling_client=docling_client,
                    config=cfg
                )
            )

            run_logger.info(f"✅ [Extract] Extraktion erfolgreich abgeschlossen. Status: {output_document.status}")
            return output_document

        except Exception as e:
            run_logger.error(f"💥 [Extract] Kritischer Fehler bei der Extraktion: {str(e)}")
            raise

