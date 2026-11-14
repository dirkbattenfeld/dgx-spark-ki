# pipeline_executor/app/pipelines/ingestion_engine/services/effect_handlers.py

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict

from rag.pipelines.rag_ingestion.wrapper import RagIngestionSingleWrapper

from pipelines.ingestion_engine.core.infrastructure import InfrastructureContext
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
    async def execute_command(context: Any, registry: Dict[Any, Callable], **kwargs: Any) -> None:
        command = getattr(context, "active_command", None)
        handler = registry.get(command)
        if handler:
            logger.debug("⚡ [Effect Runner] Führe Command aus: %s", command)
            await handler(context, **kwargs)
            setattr(context, "active_command", None)
            
            
# Hilfsfunktion, um die benötigten Clients aus dem übergebenen InfrastuctureContext,
# was über **kwargs kommt, zu extrahieren

def extract_client(client_name: str, **kwargs: Any) -> Any:
    """Zentrale Hilfsfunktion, um Clients typsicher aus dem shared_env zu fischen."""
    shared_env: InfrastructureContext = kwargs.get("shared_env")
    if not shared_env:
        raise RuntimeError("InfrastructureContext (shared_env) wurde nicht im Execution-Kontext übergeben!")
    
    client = getattr(shared_env, client_name, None)
    if not client:
        raise RuntimeError(f"Client '{client_name}' wurde im InfrastructureContext nicht gefunden!")
    return client


# Effects für Reconciler

async def effect_compute_hash(context: AssetContext, **kwargs: Any):
    storage = extract_client("storage_client", **kwargs)
    
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


async def effect_upload_s3(context: AssetContext, **kwargs: Any):
    """Führt den S3-Upload für neue oder modifizierte Dateien aus."""
    storage = extract_client("storage_client", **kwargs)
    
    local_path = "unknown"
    try:
        snapshot = getattr(context, "snapshot_item", None)
        if not snapshot or not snapshot.file_hash:
            raise ValueError("❌ [S3-Path] Kann keinen S3-Pfad generieren: snapshot_item oder file_hash fehlt.")
            
        local_path = snapshot.path
        file_hash = snapshot.file_hash
        hash_prefix = file_hash[:16]   
         
        filename = Path(local_path).name
        bucket_name = "ingestion"
        s3_path = f"s3://{bucket_name}/{hash_prefix}-{filename}"

        await asyncio.to_thread(storage.ensure_bucket_exists, bucket_name)
        
        src_uri = local_path if "://" in str(local_path) else f"file://{local_path}"
        await asyncio.to_thread(storage.copy_file, src_uri, s3_path)
        
        context.s3_path = s3_path
        context.upload_error = None
        logger.info("☁️ [Reconciler Effect] S3-Upload erfolgreich: %s -> %s", local_path, s3_path)
        
    except Exception as e:
        logger.error("❌ [Reconciler Effect] S3-Upload fehlgeschlagen für %s: %s", local_path, e, exc_info=True)
        context.upload_error = str(e)
        context.s3_path = None


PIPELINE_EFFECT_REGISTRY = {
    PipelineCommand.COMPUTE_HASH: effect_compute_hash,
    PipelineCommand.UPLOAD_S3: effect_upload_s3
}


# Effects für Job_Worker
# --- MOCK-KOMPONENTEN FÜR DIE JOB-PAYLOADS ---
import random

async def mock_delete_job_payload(context: JobContext, **kwargs: Any):
    """Mock für Qdrant Vektor-Löschung bei DELETE-Jobs."""
    job_id = context.job.job_id
    logger.info("🧹 [Job Mock Shell] Qdrant: Lösche Vektoren für Job ID: %s", job_id)
    
    context.execution_error = (
        RuntimeError("Simulierter Fehler des Mock")
        if random.random() < 0
        else None
    )


crash_counter = 0
async def mock_create_job_payload(context: JobContext, **kwargs: Any):
    """Mock für Ingestion-Pipeline (Docling, Embedding, Qdrant Upsert) bei CREATE/UPDATE-Jobs."""
    global crash_counter
    crash_counter +=1
    
    if crash_counter == -1:
        logger.error("💀 [HARD CRASH] OOM / SIGKILL / Prozess stirbt hart bei Job: %s", context.job.job_id)
        import sys
        sys.exit(42)
    
    job_id = context.job.job_id
    logger.info("🚀 [Job Mock Shell] Ingestion Pipeline: Starte Voll-Indexierung (Docling/Embedding) für Job ID: %s", job_id)
    
    context.execution_error = (
        RuntimeError("Simulierter Fehler des Mock")
        if random.random() < 0
        else None
    )


# ---- Komponenten für Job Payloads

from qdrant_client.models import FieldCondition, Filter, MatchValue


async def delete_job_payload(context: JobContext, **kwargs: Any):
    """Qdrant Vektor-Löschung bei DELETE-Jobs und UPDATE-Jobs."""
    qdrant_service = extract_client("qdrant_client", **kwargs)
    qdrant_client = qdrant_service.client
    
    job_id = context.job.job_id
    logger.info("🧹 [Delete Vectors Qdrant]: Lösche Vektoren für Job ID: %s", job_id)
    try:
        purge_filter = Filter(
            must=[FieldCondition(key="source_path", match=MatchValue(value=context.job.cloud_path))] 
        )
        print("DEBUG: ", context.job.cloud_path, "///")
        await qdrant_client.delete(collection_name="test4", points_selector=purge_filter)
        await qdrant_client.delete(collection_name="test4_parents", points_selector=purge_filter)
    except Exception as e:
        logger.error("[Ingestion Pipeline]: Fehler während der Ausführung von Job ID: %s: %s", job_id, e)
        context.execution_error = e  
    

async def create_job_payload(context: JobContext, **kwargs: Any):
    """Ingestion-Pipeline für CREATE/UPDATE-Jobs."""
    job_id = context.job.job_id
    logger.info("🚀 [Ingestion Pipeline]: Starte Voll-Indexierung für Job ID: %s", job_id)
    try:
        cloud_path = context.job.cloud_path
        payload = {"source_path": cloud_path}
        overrides = {"StoreQdrant": {"collection_name": "test4"}} # todo collection name aus job
        result = await RagIngestionSingleWrapper().execute(incoming_payload=payload, overrides=overrides)
        status = result.get("status", {})
        if status.get("status") == "failed":
            context.execution_error = status 
        logger.info("[Ingestion Pipeline]: result = %s", str(status))
    except Exception as e:
        logger.error("[Ingestion Pipeline]: Fehler während der Ausführung von Job ID: %s: %s", job_id, e)
        context.execution_error = e


async def effect_execute_job_payload(context: JobContext, **kwargs: Any):
    """Dispatcher-Weiche für Job-Payloads"""
    try:
        operation = context.job.operation
        
        logger.info("🚀 [Worker Effect] Führe Payload für Job ID aus: %s [Typ: %s]", context.job.job_id, operation)
        
        if operation == OperationType.DELETE:
            await delete_job_payload(context, **kwargs)
        elif operation == OperationType.CREATE:
            await create_job_payload(context, **kwargs)
        elif operation == OperationType.UPDATE:
            # 1. Schritt: Alte Vektoren / Orphan Chunks restlos bereinigen
            await delete_job_payload(context, **kwargs)
            
            # 2. Schritt: Nur wenn das Löschen erfolgreich war, die neue Version indexieren
            if context.execution_error is None:
                await create_job_payload(context, **kwargs)
        else:
            raise ValueError(f"Unbekannter Operationstyp im Job: {operation}")
            
    except Exception as e:
        logger.error("❌ [Worker Effect] Fehler bei Payload-Ausführung: %s", e)
        context.execution_error = e
        context.new_job_status = JobStatus.FAILED
        
        
# Komponenten für Error Handling        
async def effect_analyze_error(context: JobContext, **kwargs: Any):
    """Extrahiert die Fehlermeldung, wenn ein Fehler aufgetreten ist (Shell-Operation)."""
    if context.execution_error:
        context.error_message = str(context.execution_error)
        logger.warning("⚠️ [Worker Effect] Fehler analysiert und extrahiert: %s", context.error_message)


WORKER_EFFECT_REGISTRY = {
    JobCommand.EXECUTE_PAYLOAD: effect_execute_job_payload,
    JobCommand.ANALYZE_ERROR: effect_analyze_error
}


# Finale Persitierung der Jobs (wird nicht über den EffectExecutionRunner aufgerufen)
async def effect_persist_job_result(context: JobContext, uow: AsyncUnitOfWork, **kwargs: Any):
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



