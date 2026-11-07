# pipeline_executor/app/pipelines/ingestion_engine/services/effect_handlers.py

import hashlib
import logging
from typing import Any, Callable, Dict

from storage.client import StorageClient

from pipelines.ingestion_engine.core.models import (
    AssetContext,
    JobCommand,
    JobContext,
    JobStatus,
    OperationType,
    PipelineCommand,
)
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork

logger = logging.getLogger(__name__)


# Effect Execution Runner für Reconciler und Job_Worker
class EffectExecutionRunner:
    """Universeller Effekt-Dispatcher für alle Context-Typen (Functional Core -> Imperative Shell)."""
    @staticmethod
    async def execute_command(context: Any, registry: Dict[Any, Callable], *args, **kwargs) -> None:
        command = getattr(context, "active_command", None)
        handler = registry.get(command)
        if handler:
            logger.debug("⚡ [Effect Runner] Führe Command aus: %s", command)
            await handler(context, *args, **kwargs)
            setattr(context, "active_command", None)


# Effects für Reconciler

async def effect_compute_hash(context: AssetContext, uow: AsyncUnitOfWork, storage: StorageClient):
    if context.snapshot_item:
        file_path_str = str(context.snapshot_item.path)
        logger.info("📦 [Effect] Berechne Hash für: %s", file_path_str)
        sha256_hash = hashlib.sha256()
        try:
            full_path = storage._get_full_path(file_path_str)
            fs = storage._get_fs(full_path)
            with fs.open(full_path, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            context.snapshot_item.file_hash = sha256_hash.hexdigest()
        except Exception as e:
            logger.error("❌ Fehler bei Hash-Berechnung für '%s': %s", file_path_str, e)
            raise


PIPELINE_EFFECT_REGISTRY = {
    PipelineCommand.COMPUTE_HASH: effect_compute_hash,
}


# Effects für Job_Worker
# --- MOCK-KOMPONENTEN FÜR DIE JOB-PAYLOADS ---
import random

async def mock_delete_job_payload(context: JobContext, *args, **kwargs):
    """Mock für Qdrant Vektor-Löschung bei DELETE-Jobs."""
    job_id = context.job.job_id
    logger.info("🧹 [Job Mock Shell] Qdrant: Lösche Vektoren für Job ID: %s", job_id)
    # Späterer echter Code hier:
    # await qdrant_client.delete(collection_name=..., points_selector=...)
    context.execution_error = (
        RuntimeError("Simulierter Fehler des Mock")
        if random.random() < 0.1
        else None
    )

async def mock_create_job_payload(context: JobContext, *args, **kwargs):
    """Mock für Ingestion-Pipeline (Docling, Embedding, Qdrant Upsert) bei CREATE/UPDATE-Jobs."""
    job_id = context.job.job_id
    logger.info("🚀 [Job Mock Shell] Ingestion Pipeline: Starte Voll-Indexierung (Docling/Embedding) für Job ID: %s", job_id)
    # Späterer echter Code hier:
    # parsed_doc = await docling_parser.parse(...)
    # vectors = await embedding_generator.generate(...)
    # await qdrant_client.upsert(...)
    context.execution_error = (
        RuntimeError("Simulierter Fehler des Mock")
        if random.random() < 0.2
        else None
    )


async def effect_execute_job_payload(context: JobContext, *args, **kwargs):
    """Dispatcher-Weiche für Job-Payloads"""
    try:
        operation = context.job.operation
        
        logger.info("🚀 [Worker Effect] Führe Payload für Job ID aus: %s [Typ: %s]", context.job.job_id, operation)
        
        if operation == OperationType.DELETE:
            await mock_delete_job_payload(context, *args, **kwargs)
        elif operation == OperationType.CREATE:
            await mock_create_job_payload(context, *args, **kwargs)
        elif operation == OperationType.UPDATE:
            # 1. Schritt: Alte Vektoren / Orphan Chunks restlos bereinigen
            await mock_delete_job_payload(context, *args, **kwargs)
            
            # 2. Schritt: Nur wenn das Löschen erfolgreich war, die neue Version indexieren
            if context.execution_error is None:
                await mock_create_job_payload(context, *args, **kwargs)
        else:
            raise ValueError(f"Unbekannter Operationstyp im Job: {operation}")
            
    except Exception as e:
        logger.error("❌ [Worker Effect] Fehler bei Payload-Ausführung: %s", e)
        context.execution_error = e
        context.new_job_status = JobStatus.FAILED


async def effect_analyze_error(context: JobContext, *args, **kwargs):
    """Extrahiert die Fehlermeldung, wenn ein Fehler aufgetreten ist (Shell-Operation)."""
    if context.execution_error:
        context.error_message = str(context.execution_error)
        logger.warning("⚠️ [Worker Effect] Fehler analysiert und extrahiert: %s", context.error_message)


async def effect_persist_job_result(context: JobContext, uow: AsyncUnitOfWork, *args, **kwargs):
    """Persistiert den Job-Status und synchronisiert atomar das Asset-Ledger."""
    job_id = context.job.job_id
    logger.info("💾 [Worker Effect] Persistiere Job-Ergebnis für ID: %s [Status: %s]", job_id, context.new_job_status)
    
    await uow.repo.finalize_job_execution(
        job_id=job_id,
        new_job_status=context.new_job_status,
        increment_retry=context.increment_retry,
        error_message=context.error_message,
        error_severity=getattr(context, "error_severity", None)
    )


WORKER_EFFECT_REGISTRY = {
    JobCommand.EXECUTE_PAYLOAD: effect_execute_job_payload,
    JobCommand.ANALYZE_ERROR: effect_analyze_error,
    JobCommand.PERSIST_RESULT: effect_persist_job_result,
}
