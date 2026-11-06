# pipeline_executor/app/pipelines/ingestion_engine/db/repository.py

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pipelines.ingestion_engine.core.models import (
    AssetStatus, 
    JobStatus, 
    LedgerFieldDelta,
    JobFieldDelta,
)
from pipelines.ingestion_engine.db.models import AssetRecordModel, IngestionJobModel

logger = logging.getLogger(__name__)


class IngestionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- BASIS LOOKUPS ---
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


    # --- PHASE 2: DER REINER CRUD-DELTA-INTERPRETER ---
    async def bulk_persist_chunk(
        self, 
        ledger_mutations: List[LedgerFieldDelta], 
        job_mutations: List[JobFieldDelta], 
        vector_operations: List[dict]
    ) -> None:
        """Reiner, mechanischer Interpreter für Ledger- und Job-Deltas ohne jegliche Fachlogik."""
        
        if not ledger_mutations and not job_mutations and not vector_operations:
            return

        # 1. Vorab-Laden aller relevanten Pfade zur Vermeidung von N+1-Queries
        all_paths = [mut.file_path for mut in ledger_mutations if mut]
        existing_assets = await self.get_assets_by_paths(all_paths)
        existing_map = {str(a.file_path): a for a in existing_assets}

        # 2. Ledger-Deltas starr nach Primitiven abarbeiten (Weg A: Strikte Invarianten)
        for mut in ledger_mutations:
            if not mut:
                continue
            
            path = mut.file_path
            existing = existing_map.get(path)

            match mut.operation:
                case "insert":
                    if existing:
                        raise ValueError(f"Invarianten-Verletzung: Kann Asset {path} nicht einfügen, da es bereits existiert.")
                    
                    asset = AssetRecordModel(
                        file_path=path,
                        last_success_hash=mut.last_success_hash or "",
                        last_success_mtime=mut.last_success_mtime or datetime.now(timezone.utc),
                        status=mut.status or AssetStatus.PENDING
                    )
                    self.session.add(asset)
                    existing_map[path] = asset

                case "update_strict":
                    if not existing:
                        raise ValueError(f"Invarianten-Verletzung: Kann Asset {path} nicht aktualisieren, da es nicht existiert.")
                    
                    # Wende NUR die im Delta explizit gesetzten Felder an
                    if mut.status is not None: existing.status = mut.status
                    if mut.last_success_hash is not None: existing.last_success_hash = mut.last_success_hash
                    if mut.last_success_mtime is not None: existing.last_success_mtime = mut.last_success_mtime
                    if mut.last_error is not None: existing.last_error = mut.last_error

                case "delete":
                    if existing:
                        await self.session.delete(existing)

        # 3. Job-Deltas starr nach Primitiven abarbeiten
        for j_mut in job_mutations:
            match j_mut.delta_operation:
                case "insert":
                    job = IngestionJobModel(
                        job_id=j_mut.job_id or uuid4(),
                        asset_path=j_mut.asset_path,
                        original_path=str(j_mut.original_path),
                        cloud_path=j_mut.cloud_path,
                        operation=j_mut.operation,
                        status=j_mut.status or JobStatus.PENDING,
                        retry_count=j_mut.retry_count or 0
                    )
                    self.session.add(job)
                case "delete":
                    await self.session.execute(
                        delete(IngestionJobModel).where(IngestionJobModel.asset_path == j_mut.asset_path)
                    )

        # 4. Vector-Operationen (Stub / Logging)
        for v_op in vector_operations:
            logger.info("🧹 [Vector Operation Stub] Vektor-Löschung verzeichnet für Pfad: %s", v_op.get("path"))

        await self.session.flush()


    # --- JOB WORKER INTERPRETER ---

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
        stmt = (
            update(IngestionJobModel)
            .where(IngestionJobModel.status == JobStatus.RUNNING)
            .values(status=JobStatus.PENDING, updated_at=datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def apply_job_and_ledger_mutation(
        self,
        job_id: UUID,
        new_job_status: JobStatus,
        increment_retry: bool,
        error_message: Optional[str],
        error_severity: Optional[str],
        ledger_mutation: Optional[LedgerFieldDelta]
    ) -> None:
        """Dummer Interpreter für Worker-Ergebnisse und optionale Ledger-Deltas."""
        
        # 1. Job aktualisieren
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

        # 2. Optionales Ledger-Delta rein primitiv anwenden
        if ledger_mutation:
            asset = await self.get_by_path(ledger_mutation.file_path)
            
            match ledger_mutation.operation:
                case "delete":
                    if asset:
                        await self.session.delete(asset)
                case "update_strict":
                    if not asset:
                        raise ValueError(f"Worker-Invarianten-Fehler: Asset {ledger_mutation.file_path} existiert nicht.")
                    if ledger_mutation.status is not None: asset.status = ledger_mutation.status
                    if ledger_mutation.last_success_hash is not None: asset.last_success_hash = ledger_mutation.last_success_hash
                    if ledger_mutation.last_success_mtime is not None: asset.last_success_mtime = ledger_mutation.last_success_mtime
                    if ledger_mutation.last_error is not None: asset.last_error = ledger_mutation.last_error

        await self.session.flush()

    async def prune_jobs(self) -> dict[str, int]:
        success_stmt = delete(IngestionJobModel).where(IngestionJobModel.status == JobStatus.SUCCESS)
        success_res = await self.session.execute(success_stmt)
        
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
