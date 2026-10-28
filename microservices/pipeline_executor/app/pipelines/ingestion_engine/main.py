# pipeline_executor/app/pipelines/ingestion_engine/main.py

import asyncio
import logging
import sys
from datetime import timezone
from pathlib import Path

# Logging konfigurieren, damit wir sehen, was passiert
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("IngestionTestMain")

# --- DEBUG & EXECUTION FLAGS (Zum Ein-/Ausschalten der Pipeline-Stufen) ---
RUN_SCANNER = True
RUN_RECONCILIATION = True
INSPECT_DATABASE = True

# Alle Config Variablen kommen aus der pydantic settings!
from pipelines.ingestion_engine.core.config import settings
from pipelines.ingestion_engine.core.models import PathRuleConfig, PipelineConfig
from pipelines.ingestion_engine.services.scanner import StorageSnapshotScanner
from pipelines.ingestion_engine.services.reconciler import ReconciliationService
from pipelines.ingestion_engine.db.session import async_session_maker
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork
from pipelines.ingestion_engine.db.models import AssetRecordModel, IngestionJobModel
from sqlalchemy import select


async def run_pipeline_test():
    logger.info("🚀 Starte End-to-End Test für Ingestion-Pipeline...")

    # 1. Test-Konfiguration aufbauen
    test_target_dir = Path("/workspace/projects/rag02/data")
    test_target_dir.mkdir(exist_ok=True)

    pipeline_config = PipelineConfig(
        global_allowed_extensions=[".pdf", ".docx", ".xlsx"],
        watched_targets=[
            PathRuleConfig(
                path=test_target_dir,
                exclude_paths=[],
                exclude_extensions=[]
            )
        ]
    )

    # 2. StorageClient initialisieren
    try:
        from storage.client import StorageClient
        storage_client = StorageClient()
    except Exception as e:
        logger.warning(f"⚠️ StorageClient konnte nicht geladen werden ({e}).")
        raise

    snapshots = []

    # --- STUFE 1: SCANNER ---
    if RUN_SCANNER:
        logger.info("--- [STUFE 1] Führe Snapshot-Scan aus ---")
        scanner = StorageSnapshotScanner(config=pipeline_config, storage_client=storage_client)
        snapshots = scanner.scan()
        logger.info(f"📊 Scan beendet. Gefundene Snapshots: {len(snapshots)}")
        for snap in snapshots:
            logger.info(f"   - Pfad: {snap.path} | Größe: {snap.size_bytes} Bytes | Mtime: {snap.mtime}")
    else:
        logger.info("⏭️ Scanner übersprungen (Flag ist False).")

    # --- STUFE 2: RECONCILIATION ---
    if RUN_RECONCILIATION:
        logger.info("--- [STUFE 2] Führe Reconciliation (Delta-Abgleich) aus ---")
        if not snapshots:
            logger.warning("⚠️ Keine Snapshots vorhanden zum Abgleichen. Bitte aktiviere den Scanner oder erstelle Testdaten.")
        else:
            # Unit of Work initialisieren und Reconciler aufrufen
            uow = AsyncUnitOfWork(async_session_maker)
            reconciler = ReconciliationService(uow=uow, storage_client=storage_client, batch_size=5)
            
            jobs_created = await reconciler.reconcile(snapshots)
            logger.info(f"✨ Reconciliation beendet. Erstellte Jobs: {jobs_created}")
    else:
        logger.info("⏭️ Reconciliation übersprungen (Flag ist False).")

    # --- STUFE 3: DATABASE INSPECTION ---
    if INSPECT_DATABASE:
        logger.info("--- [STUFE 3] Inspiziere PostgreSQL Tabellen ---")
        async with async_session_maker() as session:
            # 1. asset_registry ausgeben
            res_assets = await session.execute(select(AssetRecordModel))
            assets = res_assets.scalars().all()
            logger.info("==================================================")
            logger.info("📂 TABELLE: asset_registry (%d Einträge)", len(assets))
            logger.info("==================================================")
            for a in assets:
                logger.info(
                    "Path: %s\n  -> Hash: %s... | Status: %s | Mtime: %s | DeletedAt: %s",
                    a.file_path, a.last_seen_hash[:12] if a.last_seen_hash else "None",
                    a.status, a.last_seen_mtime, a.deleted_at
                )

            # 2. ingestion_jobs ausgeben
            res_jobs = await session.execute(select(IngestionJobModel))
            jobs = res_jobs.scalars().all()
            logger.info("==================================================")
            logger.info("⚙️ TABELLE: ingestion_jobs (%d Einträge)", len(jobs))
            logger.info("==================================================")
            for j in jobs:
                logger.info(
                    "Job ID: %s\n  -> Asset: %s\n  -> Operation: %s | Status: %s | CloudPath: %s",
                    j.job_id, j.asset_path, j.operation, j.status, j.cloud_path
                )
            logger.info("==================================================")
    else:
        logger.info("⏭️ Datenbank-Inspektion übersprungen (Flag ist False).")


if __name__ == "__main__":
    asyncio.run(run_pipeline_test())
