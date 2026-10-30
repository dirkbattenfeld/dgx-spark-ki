# pipeline_executor/app/pipelines/ingestion_engine/services/effect_handlers.py

import hashlib
import logging
from typing import Any, Callable, Dict

from storage.client import StorageClient

from pipelines.ingestion_engine.core.models import (
    AssetContext,
    JobContext,
    PipelineCommand,
)
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork

logger = logging.getLogger(__name__)


class EffectExecutionRunner:
    @staticmethod
    async def execute_command(context: AssetContext, registry: Dict[PipelineCommand, Callable], *args, **kwargs) -> None:
        handler = registry.get(context.active_command)
        if handler:
            logger.debug("⚡ [Effect Runner] Führe Command aus: %s", context.active_command)
            await handler(context, *args, **kwargs)
            context.active_command = PipelineCommand.NONE


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


async def effect_execute_job_payload(context: JobContext, uow: AsyncUnitOfWork):
    try:
        logger.info("🚀 [Worker Effect] Payload Ausführung für Job ID: %s", context.job.job_id)
    except Exception as e:
        context.execution_error = e


async def effect_analyze_error(context: JobContext, uow: AsyncUnitOfWork):
    if context.execution_error:
        context.error_message = str(context.execution_error)


async def effect_persist_job_result(context: JobContext, uow: AsyncUnitOfWork):
    job = context.job
    job.status = context.new_job_status
    if context.increment_retry:
        job.retry_count += 1
    if context.error_message:
        job.stacktrace = context.error_message
