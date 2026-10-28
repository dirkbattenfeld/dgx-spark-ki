# pipelines/ingestion_engine/services/reconciler.py

import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Set
from uuid import uuid4

from storage.client import StorageClient

from pipelines.ingestion_engine.core.models import (
    AssetStatus,
    FileSnapshot,
    JobStatus,
    OperationType,
)
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork

logger = logging.getLogger(__name__)


class ReconciliationService:
    def __init__(self, uow: AsyncUnitOfWork, storage_client: StorageClient, batch_size: int = 5):
        self.uow = uow
        self.storage = storage_client
        self.batch_size = batch_size

    async def reconcile(self, snapshots: List[FileSnapshot]) -> int:
        """
        Führt den vollständigen Delta-Abgleich durch:
        1. Batch-Verarbeitung der gescannten Snapshots.
        2. Zweistufige Logik (mtime/size-Prüfung vor teurem Hash).
        3. Behandlung von reaktivierten (zuvor gelöschten) Dateien.
        4. Erkennung und Markierung gelöschter (verwaister) Dateien.
        """
        logger.info("🔄 Starte Reconciliation-Prozess (Delta-Abgleich)...총 %d Snapshots", len(snapshots))
        total_jobs_created = 0
        scanned_paths: Set[str] = {str(s.path) for s in snapshots}

        # --- SCHRITT 1: SNAPSHOTS IN BATCHES VERARBEITEN ---
        for i in range(0, len(snapshots), self.batch_size):
            batch = snapshots[i : i + self.batch_size]
            batch_paths = [str(s.path) for s in batch]

            # Transaktionsgrenze via Unit of Work
            async with self.uow as uow:
                # Bulk-Lookup im Ledger für diesen Batch
                existing_assets = await uow.repo.get_assets_by_paths(batch_paths)
                existing_map = {asset.file_path: asset for asset in existing_assets}

                for snap in batch:
                    path_str = str(snap.path)
                    existing_asset = existing_map.get(path_str)

                    # Fall A: Datei ist völlig neu im Ledger
                    if existing_asset is None:
                        logger.info("📄 Neues Asset erkannt: %s", path_str)
                        file_hash = self._compute_file_hash(path_str)

                        await uow.repo.create_asset(
                            file_path=path_str,
                            last_seen_hash=file_hash,
                            last_seen_mtime=snap.mtime,
                            status=AssetStatus.PENDING,
                        )
                        await self._create_job(uow, path_str, OperationType.CREATE)
                        total_jobs_created += 1
                        continue

                    # Fall B: Datei existiert im Ledger, war aber als DELETED markiert (Reaktivierung)
                    if existing_asset.status == AssetStatus.DELETED:
                        logger.info("♻️ Zuvor gelöschtes Asset reaktiviert: %s", path_str)
                        file_hash = self._compute_file_hash(path_str)
                        
                        # Prüfen, ob sich der Inhalt im Vergleich zum alten Hash geändert hat
                        is_modified = (file_hash != existing_asset.last_seen_hash)
                        
                        existing_asset.last_seen_hash = file_hash
                        existing_asset.last_seen_mtime = snap.mtime
                        existing_asset.status = AssetStatus.PENDING
                        existing_asset.deleted_at = None

                        op_type = OperationType.UPDATE if is_modified else OperationType.CREATE
                        await self._create_job(uow, path_str, op_type)
                        total_jobs_created += 1
                        continue

                    # Fall C: Datei existiert und ist aktiv -> Zweistufige Logik (mtime-Prüfung)
                    # Wenn mtime exakt übereinstimmt, überspringen wir die teure Hash-Berechnung!
                    if existing_asset.last_seen_mtime == snap.mtime:
                        logger.debug("⏩ Keine Änderung (mtime identisch): %s", path_str)
                        continue

                    # mtime hat sich geändert -> Zweite Stufe: Hash berechnen
                    logger.info("🔄 Modifiziertes Asset erkannt (mtime hat sich geändert): %s", path_str)
                    file_hash = self._compute_file_hash(path_str)

                    # Wenn der Hash sich tatsächlich unterscheidet, ist es ein echtes Update
                    if file_hash != existing_asset.last_seen_hash:
                        logger.info("📝 Hash-Änderung verifiziert für: %s", path_str)
                        existing_asset.last_seen_hash = file_hash
                        existing_asset.last_seen_mtime = snap.mtime
                        existing_asset.status = AssetStatus.PENDING
                        existing_asset.deleted_at = None

                        await self._create_job(uow, path_str, OperationType.UPDATE)
                        total_jobs_created += 1
                    else:
                        # Nur mtime berührt, Inhalt ist identisch -> nur mtime aktualisieren, kein Job
                        existing_asset.last_seen_mtime = snap.mtime

        # --- SCHRITT 2: ERKENNUNG GELÖSCHTER DATEIEN (ORPHAN CLEANUP) ---
        async with self.uow as uow:
            all_active_assets = await uow.repo.get_active_assets()
            
            for asset in all_active_assets:
                if asset.file_path not in scanned_paths:
                    logger.warning("🗑️ Gelöschte Datei im Dateisystem erkannt: %s", asset.file_path)
                    
                    # Asset als gelöscht markieren (Soft Delete)
                    asset.status = AssetStatus.DELETED
                    asset.deleted_at = datetime.now(timezone.utc)

                    # Lösch-Job in die Queue schreiben
                    await self._create_job(uow, asset.file_path, OperationType.DELETE)
                    total_jobs_created += 1

        logger.info("✨ Reconciliation erfolgreich beendet. %d Jobs erstellt.", total_jobs_created)
        return total_jobs_created

    def _compute_file_hash(self, file_path_str: str) -> str:
        """Berechnet den SHA-256 Hash einer Datei streaming-basiert über den StorageClient."""
        sha256_hash = hashlib.sha256()
        try:
            full_path = self.storage._get_full_path(file_path_str)
            fs = self.storage._get_fs(full_path)
            with fs.open(full_path, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error("❌ Fehler bei der Hash-Berechnung für '%s': %s", file_path_str, e)
            raise

    async def _create_job(self, uow: AsyncUnitOfWork, file_path: str, operation: OperationType):
        """Hilfsmethode zum Erstellen eines Ingestion-Jobs verknüpft mit dem Asset."""
        job_id = uuid4()
        # Staging-Cloud-Ziel definieren (z.B. S3-Bucket Pfad basierend auf Dateinamen)
        filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + str(file_path).split("/")[-1]
        cloud_target_path = f"s3://staging-bucket/{filename}"

        await uow.repo.create_job(
            job_id=job_id,
            asset_path=file_path,
            original_path=file_path,
            cloud_path=cloud_target_path,
            operation=operation,
        )
