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
RUN_JOB_WORKER = False
INSPECT_DATABASE = True

from pipelines.ingestion_engine.core.config import settings
from pipelines.ingestion_engine.core.models import PathRuleConfig, PipelineConfig
from pipelines.ingestion_engine.db.models import AssetRecordModel, IngestionJobModel
from pipelines.ingestion_engine.db.session import async_session_maker
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork
from pipelines.ingestion_engine.services.job_worker import run_job_worker_loop
from pipelines.ingestion_engine.services.reconciler import ReconciliationService
from pipelines.ingestion_engine.services.scanner import StorageSnapshotScanner


async def run_pipeline_test():
    logger.info("🚀 Starte End-to-End Test für generative Ingestion-Pipeline...")

    test_target_dir = Path("/workspace/projects/rag02/data")
    test_target_dir.mkdir(exist_ok=True, parents=True)

    pipeline_config = PipelineConfig(
        global_allowed_extensions=[".pdf", ".docx", ".xlsx", ".pptx"],
        watched_targets=[PathRuleConfig(path=test_target_dir)]
    )

    try:
        from storage.client import StorageClient
        storage_client = StorageClient()
    except Exception as e:
        logger.warning(f"⚠️ StorageClient konnte nicht geladen werden ({e}).")
        raise

    snapshots = []

    if RUN_SCANNER:
        logger.info("--- [SCAN] Snapshot-Scan ---")
        scanner = StorageSnapshotScanner(config=pipeline_config, storage_client=storage_client)
        snapshots = scanner.scan()
        logger.info("📊 Snapshots gefunden: %d", len(snapshots))

    if RUN_RECONCILIATION:
        logger.info("--- [RECONCILE] Chunked Reconciler & 3-Stage Pipeline ---")
        if snapshots:
            uow = AsyncUnitOfWork(async_session_maker)
            reconciler = ReconciliationService(uow=uow, storage_client=storage_client)
            await reconciler.reconcile(snapshots)

    if RUN_JOB_WORKER:
        logger.info("--- [WORKER] Job Worker Execution (Isolated Transactions) ---")
        await run_job_worker_loop(async_session_maker)

    if INSPECT_DATABASE:
        logger.info("--- [INSPECT] PostgreSQL State Inspection ---")
        async with async_session_maker() as session:
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


if __name__ == "__main__":
    asyncio.run(run_pipeline_test())
