# pipeline_executor/app/pipelines/ingestion_engine/db/repository.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pipelines.ingestion_engine.core.models import AssetStatus, JobStatus, OperationType
from pipelines.ingestion_engine.db.models import AssetRecordModel, IngestionJobModel

logger = logging.getLogger(__name__)


class IngestionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

# Asset Registry Ledger Operations im Reconciler
    async def get_by_hash(self, file_hash: str) -> Optional[AssetRecordModel]:
        result = await self.session.execute(
            select(AssetRecordModel).where(AssetRecordModel.last_seen_hash == file_hash)
        )
        return result.scalars().first()

    async def get_by_path(self, file_path: str) -> Optional[AssetRecordModel]:
        result = await self.session.execute(
            select(AssetRecordModel).where(AssetRecordModel.file_path == file_path)
        )
        return result.scalars().first()

    async def get_assets_by_paths(self, file_paths: List[str]) -> List[AssetRecordModel]:
        if not file_paths:
            return []
        result = await self.session.execute(
            select(AssetRecordModel).where(AssetRecordModel.file_path.in_(file_paths))
        )
        return list(result.scalars().all())

    async def get_active_assets(self) -> List[AssetRecordModel]:
        result = await self.session.execute(
            select(AssetRecordModel).where(AssetRecordModel.status != AssetStatus.DELETED)
        )
        return list(result.scalars().all())

    async def update_asset_path(self, old_path: str, new_path: str) -> None:
        stmt = (
            update(AssetRecordModel)
            .where(AssetRecordModel.file_path == old_path)
            .values(file_path=new_path, updated_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def mark_asset_deleted(self, file_path: str) -> None:
        stmt = (
            update(AssetRecordModel)
            .where(AssetRecordModel.file_path == file_path)
            .values(status=AssetStatus.DELETED, deleted_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)


# LEDGER UND JobList: Ein Batch von Ergebnissen im Reconciler in den Ledger und die JobList persistieren
    async def bulk_persist_chunk(
        self, 
        ledger_mutations: List[Dict[str, Any]], 
        job_mutations: List[Dict[str, Any]], 
        vector_operations: List[Dict[str, Any]]
    ) -> None:
        """Echtes Batching: Vorab-Laden vorhandener Assets, um N+1-Query-Probleme zu verhindern."""
        
        # 1. Vorab-Laden aller relevanten Upsert-Pfade in einem einzigen .in_()-Query
        upsert_paths = [mut["file_path"] for mut in ledger_mutations if mut.get("action") == "upsert"]
        existing_assets = await self.get_assets_by_paths(upsert_paths)
        existing_map = {a.file_path: a for a in existing_assets}

        # 2. Ledger-Mutationen abarbeiten
        for mut in ledger_mutations:
            if not mut:  # Überspringe None-Mutationen (z.B. bei SKIP)
                continue
            action = mut.get("action")
            if action == "upsert":
                path = mut["file_path"]
                file_hash = mut.get("hash")
                if not file_hash:
                    continue  # Niemals ohne Hash upserten!
                                
                existing = existing_map.get(path)
                if existing:
                    existing.last_seen_hash = mut["hash"]
                    existing.last_seen_mtime = mut["mtime"]
                    existing.status = AssetStatus.PENDING
                    existing.deleted_at = None
                else:
                    asset = AssetRecordModel(
                        file_path=path,
                        last_seen_hash=mut["hash"],
                        last_seen_mtime=mut["mtime"],
                        status=AssetStatus.PENDING
                    )
                    self.session.add(asset)
            elif action == "move":
                await self.update_asset_path(mut["old_path"], mut["new_path"])
            elif action == "delete":
                await self.mark_asset_deleted(mut["file_path"])
            elif action == "cancel_pending":  
                path = mut["file_path"]
                # 1. Hängende Pending-Jobs für diesen Pfad löschen
                await self.session.execute(
                    delete(IngestionJobModel).where(
                        IngestionJobModel.asset_path == path,
                        IngestionJobModel.status == JobStatus.PENDING
                    )
                )
                # 2. Un-synced Ledger-Eintrag komplett entfernen (da nie in Cloud/Vektorspeicher)
                existing = existing_map.get(path) or await self.get_by_path(path)
                if existing:
                    await self.session.delete(existing)

        # 3. Job-Mutationen mit sicherer uuid4() generieren
        for j_mut in job_mutations:
            job = IngestionJobModel(
                job_id=uuid4(),
                asset_path=j_mut["asset_path"],
                original_path=j_mut["asset_path"],
                cloud_path=j_mut["cloud_path"],
                operation=OperationType(j_mut["operation"]),
                status=JobStatus.PENDING
            )
            self.session.add(job)

        # 4. Vector-Operationen (Stub / Logging)
        for v_op in vector_operations:
            logger.info("🧹 [Vector Operation Stub] Vektor-Löschung verzeichnet für Pfad: %s", v_op.get("path"))

        await self.session.flush()

# JobList Operations
    async def fetch_next_pending_job_with_skip_locked(self) -> Optional[IngestionJobModel]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.status == JobStatus.PENDING)
            .order_by(IngestionJobModel.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.status = JobStatus.RUNNING
            await self.session.flush()
        return job

    async def reset_running_jobs_to_pending(self) -> int:
        """Setzt hängengebliebene RUNNING-Jobs beim Startup auf PENDING zurück und gibt die Anzahl zurück."""
        stmt = (
            update(IngestionJobModel)
            .where(IngestionJobModel.status == JobStatus.RUNNING)
            .values(status=JobStatus.PENDING, updated_at=datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        return result.rowcount


    async def finalize_job_execution(
        self, 
        job_id: str, 
        new_job_status: JobStatus, 
        increment_retry: bool, 
        error_message: str | None,
        error_severity: str | None = None
    ):
        # 1. Job holen und Status updaten (Dein robuster Original-Code)
        job = await self.session.get(IngestionJobModel, job_id)
        if not job:
            return

        job.status = new_job_status
        job.updated_at = datetime.now(timezone.utc)
        
        if new_job_status in (JobStatus.SUCCESS, JobStatus.DEAD_LETTER):
            job.finished_at = datetime.now(timezone.utc)

        if increment_retry:
            job.retry_count += 1
            
        if error_message:
            job.stacktrace = error_message
            
        if error_severity and hasattr(job, "error_severity"):
            job.error_severity = error_severity

        # 2. Zugehöriges Asset im Ledger synchronisieren (Mit Operation-Weiche)
        target_path = getattr(job, "asset_path", None)
        job_operation = getattr(job, "operation", None)

        if target_path:
            if new_job_status == JobStatus.SUCCESS:
                # KORREKTUR: Unterscheidung zwischen DELETE und CREATE/UPDATE-Jobs
                if job_operation == OperationType.DELETE:
                    # Bei erfolgreichem Delete-Job: Asset aus dem Ledger entfernen, 
                    # damit es nicht fälschlicherweise als SYNCED reaktiviert wird!
                    asset = await self.get_by_path(target_path)
                    if asset:
                        await self.session.delete(asset)
                        logger.info("🗑️ [Ledger Sync] Asset erfolgreich aus Ledger entfernt für gelöschten Pfad: %s", target_path)
                else:
                    # Standard für CREATE / UPDATE: Auf SYNCED setzen
                    asset = await self.get_by_path(target_path)
                    if asset:
                        asset.status = AssetStatus.SYNCED
                        asset.last_synced_at = datetime.now(timezone.utc)
                        logger.info("🟢 [Ledger Sync] Asset status auf SYNCED gesetzt für: %s", target_path)
                        
            elif new_job_status == JobStatus.DEAD_LETTER:
                asset = await self.get_by_path(target_path)
                if asset:
                    asset.status = AssetStatus.FAILED
                    logger.warning("🔴 [Ledger Sync] Asset status auf FAILED gesetzt für: %s", target_path)
   
                    
    async def prune_jobs(self) -> dict[str, int]:
        # 1. Success-Jobs sofort löschen (0 Tage Retention)
        success_stmt = delete(IngestionJobModel).where(IngestionJobModel.status == JobStatus.SUCCESS)
        success_res = await self.session.execute(success_stmt)
        
        # 2. Dead-Letter-Jobs nach 30 Tagen löschen
        cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
        dl_stmt = delete(IngestionJobModel).where(
            IngestionJobModel.status == JobStatus.DEAD_LETTER,
            IngestionJobModel.updated_at < cutoff_30d
        )
        dl_res = await self.session.execute(dl_stmt)
        
        return {
            "pruned_success": success_res.rowcount,
            "pruned_dead_letter": dl_res.rowcount
        }