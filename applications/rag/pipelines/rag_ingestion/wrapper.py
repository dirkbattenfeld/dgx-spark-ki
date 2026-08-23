# applications/rag/pipelines/rag_ingestion/wrapper.py
# Wrappt die gesamte RAG Ingestion pipeline, so dass sie über eine Registry
# mit einer factory gebaut werden kann und über eine generische FastAPIBridge
# bereitgestellt werden kann 
# 1. RagIngestionSingleWrapper: Erwartet {"source_path": "Pfad"}
# 2. RagIngestionStreamingWarapper: Erwartet bucket name / directory und führt einen scan durch

import logging
from typing import Any, Literal, Optional, Type, Union

from applications.rag.pipelines.rag_ingestion.config import RagIngestionConfig
from applications.rag.pipelines.rag_ingestion.pipeline import RagIngestionPipeline
from libs.pipeline.runner import BasePipelineRunner
from libs.pipeline.wrapper import BasePipelineWrapper

logger = logging.getLogger(__name__)


class RagIngestionSingleWrapper(BasePipelineWrapper):
    """
    Spezifischer Wrapper für die RAG Ingestion Pipeline.
    """

    @property
    def pipeline_id(self) -> str:
        return "rag_ingestion_single"

    @property
    def pipeline_class(self) -> Type[RagIngestionPipeline]:
        return RagIngestionPipeline

    @property
    def config_class(self) -> Type[RagIngestionConfig]:
        return RagIngestionConfig

    @property
    def mode(self) -> Literal["single", "streaming"]:
        return "single"

    async def prepare_payloads(
        self,
        runner: BasePipelineRunner,
        config: RagIngestionConfig,
        incoming_payload: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        
        if not incoming_payload or "source_path" not in incoming_payload :
            logger.error("❌ [SingleWrapper] Kein Payload übergeben. Im Single-Modus wird ein initialer Input benötigt.")
            return []
        return [incoming_payload]


    async def process_results(
        self,
        raw_results: list[Any],
        config: RagIngestionConfig,
    ) -> dict[str, Any]:
        
        # DEBUG
        from libs.observability.helper import format_dict_tree
        print("\nDEBUG (process_results / raw_results):","="*60)
        print(format_dict_tree(raw_results))
        print("\n", "="*60)
        # DEBUG
        
        # Relevante Step-Pfade für jede Datei
        status_paths = [
            "Extract.status",
            "Chunk.status",
            "Contextualize.status",
            "Embeddings.status",
            "StoreQdrant.status",
        ]

        status_report = self.aggregate_statuses_from_paths(raw_results, status_paths)
        
        return {
            "results": raw_results,
            "status": status_report
        }

class RagIngestionStreamingWrapper(BasePipelineWrapper):
    """
    Spezifischer Wrapper für die RAG Ingestion Pipeline.
    Implementiert das Dateiscan-Intro über das Runner-Environment.
    """

    @property
    def pipeline_id(self) -> str:
        return "rag_ingestion_streaming"

    @property
    def pipeline_class(self) -> Type[RagIngestionPipeline]:
        return RagIngestionPipeline

    @property
    def config_class(self) -> Type[RagIngestionConfig]:
        return RagIngestionConfig

    @property
    def mode(self) -> Literal["single", "streaming"]:
        return "streaming"

    async def prepare_payloads(
        self,
        runner: BasePipelineRunner,
        config: RagIngestionConfig,
        incoming_payload: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        
        # Im Streaming-Modus ist der Bucket Pflicht im Payload
        if not incoming_payload or "s3_bucket" not in incoming_payload:
            logger.error("❌ [Streaming] Es wird zwingend ein Payload mit 's3_bucket' benötigt.")
            return []
            
        target_bucket = incoming_payload["s3_bucket"]

        # INTRO: S3/Dateiscan über das im Runner gekapselte Environment
        if hasattr(runner.env, "scan_source_files"):
            # Prüfen, ob in der Config/im Environment ein dynamischer Bucket-Override liegt
            # (Alternativ kann man hier auch direkt aus einem Standard-Dictionary greifen)
            pdf_paths = runner.env.scan_source_files(override_bucket=target_bucket)
            if not pdf_paths:
                logger.error(
                    "❌ Keine Dateien (%s) auf S3/Quelle gefunden.",
                    config.env.s3_glob_pattern,
                    target_bucket
                )
                return []
            return [{"source_path": path} for path in pdf_paths]

        return []

        
    async def process_results(
        self,
        raw_results: list[Any],
        config: RagIngestionConfig,
    ) -> dict[str, Any]:
        """
        OUTRO: Individuelle Aggregation und Projektion der Ingestion-Ergebnisse.
        Reduziert massive Pipeline-States (Chunks/Vectors) auf eine schlanke API-Antwort.
        """
        
        # DEBUG
        from libs.observability.helper import format_dict_tree
        print("\nDEBUG (process_results / raw_results):","="*60)
        print(format_dict_tree(raw_results))
        print("\n", "="*60)
        # DEBUG

        total_files = len(raw_results)
        total_chunks_stored = 0
        total_parent_chunks_stored = 0        
        
        first_item = raw_results[0] if raw_results else None
        run_id = self._get_by_path(first_item, "_meta.run_id") if first_item else None
        collection_name = self._get_by_path(first_item, "StoreQdrant.extras.collection") if first_item else None
        
        file_reports: list[dict[str, Any]] = []
        file_statuses: list[str] = []

        # Relevante Step-Pfade für jede Datei
        status_paths = [
            "Extract.status",
            "Chunk.status",
            "Contextualize.status",
            "Embeddings.status",
            "StoreQdrant.status",
        ]

        for item in raw_results:
            # 1. Detaillierten Status-Report für das Listenelement erstellen (Punkt 2)
            # Nutzt direkt den Eintrag (Egal ob Dict, Pydantic-Model etc.)
            status_report = self.aggregate_statuses_from_paths(item, status_paths)
            file_status = status_report["status"]
            file_statuses.append(file_status)

            # Meta-Infos auslesen
            source_path = (
                self._get_by_path(item, "Extract.source_path")
                or self._get_by_path(item, "StoreQdrant.source_path")
                or "unknown"
            )

            chunks_count = self._get_by_path(item, "StoreQdrant.chunks_stored") or 0
            parents_count = self._get_by_path(item, "StoreQdrant.parent_chunks_stored") or 0

            # Metrics für erfolgreiche Chunks summieren
            if file_status == "success":
                total_chunks_stored += chunks_count
                total_parent_chunks_stored += parents_count

            # 2. File-Report aufbauen (Punkt 2)
            file_reports.append({
                "source_path": source_path,
                "status": status_report,  # Enthält jetzt {"status": "...", "steps": {...}}
                "chunks_stored": chunks_count,
                "parent_chunks_stored": parents_count,
            })

        # 3. Globale Metriken berechnen (Punkte 3, 4, 5)
        pipeline_status = self.aggregate_status(file_statuses)
        successful_files = sum(1 for s in file_statuses if s == "success")
        failed_files = total_files - successful_files

        # 4. Der neue schlanke Output (ohne 'errors'-Sammlung)
        return {
            "pipeline_status": pipeline_status,
            "run_id": run_id,
            "summary": {
                "total_files": total_files,
                "successful_files": successful_files,
                "failed_files": failed_files,
                "total_chunks_stored": total_chunks_stored,
                "total_parents_stored": total_parent_chunks_stored,
                "collection_name": collection_name,
            },
            "processed_files": file_reports,
        }    