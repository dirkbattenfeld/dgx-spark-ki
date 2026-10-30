# pipeline_executor/app/pipelines/ingestion_engine/services/effect_handlers.py

import hashlib
import logging
from typing import Any, Callable, Dict

from storage.client import StorageClient

from pipelines.ingestion_engine.core.models import (
    AssetContext,
    JobCommand,
    JobContext,
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


async def effect_detect_move(context: AssetContext, uow: AsyncUnitOfWork, storage: StorageClient):
    if context.snapshot_item and not context.snapshot_item.file_hash:
        await effect_compute_hash(context, uow, storage)

    if context.snapshot_item and context.snapshot_item.file_hash and not context.ledger_record:
        existing = await uow.repo.get_by_hash(context.snapshot_item.file_hash)
        if existing:
            context.detected_old_path = existing.file_path
            context.detected_new_path = context.path
            logger.info("🚚 [Effect] Move erkannt: '%s' -> '%s'", existing.file_path, context.path)


PIPELINE_EFFECT_REGISTRY = {
    PipelineCommand.COMPUTE_HASH: effect_compute_hash,
    PipelineCommand.DETECT_MOVE: effect_detect_move,
}


# Effects für Job_Worker
# --- MOCK-KOMPONENTEN FÜR DIE JOB-PAYLOADS ---

async def mock_delete_job_payload(context: JobContext, *args, **kwargs):
    """Mock für Qdrant Vektor-Löschung bei DELETE-Jobs."""
    job_id = context.job.job_id
    logger.info("🧹 [Job Mock Shell] Qdrant: Lösche Vektoren für Job ID: %s", job_id)
    # Späterer echter Code hier:
    # await qdrant_client.delete(collection_name=..., points_selector=...)
    context.new_job_status = JobStatus.SUCCESS


async def mock_create_job_payload(context: JobContext, *args, **kwargs):
    """Mock für Ingestion-Pipeline (Docling, Embedding, Qdrant Upsert) bei CREATE/UPDATE-Jobs."""
    job_id = context.job.job_id
    logger.info("🚀 [Job Mock Shell] Ingestion Pipeline: Starte Voll-Indexierung (Docling/Embedding) für Job ID: %s", job_id)
    # Späterer echter Code hier:
    # parsed_doc = await docling_parser.parse(...)
    # vectors = await embedding_generator.generate(...)
    # await qdrant_client.upsert(...)
    context.new_job_status = JobStatus.SUCCESS


async def effect_execute_job_payload(context: JobContext, *args, **kwargs):
    """Dispatcher-Weiche für Job-Payloads (DELETE vs. CREATE/INDEX)."""
    try:
        # Ermittle den Job-Typ (je nach Modellfeld z.B. job_type, action oder payload_type)
        job_type = getattr(context.job, "job_type", "CREATE")
        
        logger.info("🚀 [Worker Effect] Führe Payload für Job ID aus: %s [Typ: %s]", context.job.job_id, job_type)
        
        if job_type == "DELETE":
            await mock_delete_job_payload(context, *args, **kwargs)
        else:
            # Standard: CREATE / INDEX / UPDATE
            await mock_create_job_payload(context, *args, **kwargs)
            
    except Exception as e:
        logger.error("❌ [Worker Effect] Fehler bei Payload-Ausführung: %s", e)
        context.execution_error = e
        context.new_job_status = JobStatus.FAILED


async def effect_analyze_error(context: JobContext, *args, **kwargs):
    """Extrahiert die Fehlermeldung, wenn ein Fehler aufgetreten ist (Shell-Operation)."""
    if context.execution_error:
        context.error_message = str(context.execution_error)
        logger.warning("⚠️ [Worker Effect] Fehler analysiert und extrahiert: %s", context.error_message)


async def effect_persist_job_result(context: JobContext, *args, **kwargs):
    """Bereitet das persistente Ergebnis vor."""
    logger.info("💾 [Worker Effect] Persistenz-Schritt vorbereitet für Status: %s", context.new_job_status)


WORKER_EFFECT_REGISTRY = {
    JobCommand.EXECUTE_PAYLOAD: effect_execute_job_payload,
    JobCommand.ANALYZE_ERROR: effect_analyze_error,
    JobCommand.PERSIST_RESULT: effect_persist_job_result,
}
