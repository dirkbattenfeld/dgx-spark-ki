# pipeline_executor/app/pipelines/ingestion_engine/main.py

import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("IngestionTestMain")

RUN_SCANNER = True
RUN_RECONCILIATION = True 
RUN_JOB_WORKER = True
INSPECT_DATABASE = True

from pipelines.ingestion_engine.core.config import settings
from pipelines.ingestion_engine.core.infrastructure import InfrastructureContext
from pipelines.ingestion_engine.core.models import PathRuleConfig, PipelineConfig
from pipelines.ingestion_engine.db.models import AssetRecordModel, IngestionJobModel
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork
from pipelines.ingestion_engine.services.job_worker import JobWorkerService
from pipelines.ingestion_engine.services.reconciler import ReconciliationService
from pipelines.ingestion_engine.services.scanner import StorageSnapshotScanner


async def inspect_database_state(session_maker, stage_label: str):
    """Kapselt die Inspektion beider Tabellen für transparente Zwischen- und Endstände."""
    logger.info("")  # Leerzeile
    logger.info("-" * 50)  
    logger.info("--- [INSPECT] PostgreSQL State Inspection (%s) ---", stage_label)
    async with session_maker() as session:
        res_assets = await session.execute(select(AssetRecordModel))
        assets = res_assets.scalars().all()
        logger.info("📂 ASSET REGISTRY (%d Einträge):", len(assets))
        for a in assets:
            logger.info("   - Path: %s | Status: %s", a.file_path, a.status)

        res_jobs = await session.execute(select(IngestionJobModel))
        jobs = res_jobs.scalars().all()
        logger.info("⚙️ INGESTION JOBS (%d Einträge):", len(jobs))
        for j in jobs:
            logger.info("   - ID: %s | Op: %s | Status: %s", j.job_id, j.operation, j.status)
    logger.info("-" * 50)
    logger.info("")  # Leerzeile


async def run_ingestion_engine():
    logger.info("🚀 Starte End-to-End Test für generative Ingestion-Pipeline...")

    test_target_dir = Path("/workspace/projects/rag02/data")
    test_target_dir.mkdir(exist_ok=True, parents=True)

    pipeline_config = PipelineConfig(
        global_allowed_extensions=[".pdf", ".docx", ".xlsx", ".pptx"],
        watched_targets=[PathRuleConfig(path=test_target_dir)]
    )

    infra = await InfrastructureContext.create(settings)
    
    snapshots = []

    if INSPECT_DATABASE:
        await inspect_database_state(infra.async_session_maker, "DB: Start des Skripts")
    
    if RUN_SCANNER:
        logger.info("--- [SCAN] Snapshot-Scan ---")
        scanner = StorageSnapshotScanner(config=pipeline_config, storage_client=infra.storage_client)
        snapshots = scanner.scan()
        logger.info("📊 Snapshots gefunden: %d", len(snapshots))

    if RUN_RECONCILIATION:
        logger.info ("")
        logger.info("--- [RECONCILE] Chunked Reconciler & 3-Stage Pipeline ---")
        uow = AsyncUnitOfWork(infra.async_session_maker)
        reconciler = ReconciliationService(uow=uow, shared_env=infra)
        await reconciler.reconcile(snapshots)

    if INSPECT_DATABASE:
        await inspect_database_state(infra.async_session_maker, "DB: Post-Reconciliation (Pending Jobs erstellt)")

    if RUN_JOB_WORKER:
        logger.info("--- [WORKER] Job Worker Execution (Isolated Transactions) ---")
        worker = JobWorkerService(
            max_concurrency=1,
            shared_env=infra)
        
        await worker.run_worker_loop()
        
    if INSPECT_DATABASE:
        await inspect_database_state(infra.async_session_maker, "DB: Post-Worker Execution (Jobs Success & Assets Synced)")

if __name__ == "__main__":
    asyncio.run(run_ingestion_engine())
