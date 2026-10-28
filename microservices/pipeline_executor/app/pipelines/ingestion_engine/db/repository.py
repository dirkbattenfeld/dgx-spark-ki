# /pipeline_executor/app/pipelines/ingestion_engine/db/repository.py

from collections.abc import Sequence
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipelines.ingestion_engine.core.models import (
    AssetStatus,
    JobStatus,
    OperationType,
)
from pipelines.ingestion_engine.db.models import (
    AssetRecordModel,
    IngestionJobModel,
)


class IngestionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- ASSET LEDGER OPERATIONEN ---

    async def get_by_hash(self, file_hash: str) -> Optional[AssetRecordModel]:
        """Sucht ein Asset anhand seines SHA-256 Hashes (wichtig für Deduplizierung / Move Detection)."""
        result = await self.session.execute(
            select(AssetRecordModel).where(AssetRecordModel.last_seen_hash == file_hash)
        )
        return result.scalars().first()

    async def get_by_path(self, file_path: str) -> Optional[AssetRecordModel]:
        """Sucht ein Asset anhand seines exakten Dateipfads."""
        result = await self.session.execute(
            select(AssetRecordModel).where(AssetRecordModel.file_path == file_path)
        )
        return result.scalars().first()
    
    async def get_assets_by_paths(self, file_paths: list[str]) -> list[AssetRecordModel]:
        """Holt mehrere Assets per Bulk-Query (verhindert N+1-Abfragen)."""
        result = await self.session.execute(
            select(AssetRecordModel).where(AssetRecordModel.file_path.in_(file_paths))
        )
        return list(result.scalars().all())

    async def get_active_assets(self) -> list[AssetRecordModel]:
        """Gibt alle Assets zurück, die nicht als gelöscht markiert sind."""
        result = await self.session.execute(
            select(AssetRecordModel).where(AssetRecordModel.status != AssetStatus.DELETED)
        )
        return list(result.scalars().all())

    async def create_asset(
        self, 
        file_path: str, 
        last_seen_hash: str, 
        last_seen_mtime: datetime,
        status: AssetStatus = AssetStatus.PENDING
    ) -> AssetRecordModel:
        """Legt einen neuen Asset-Eintrag im Ledger an."""
        asset = AssetRecordModel(
            file_path=file_path,
            last_seen_hash=last_seen_hash,
            last_seen_mtime=last_seen_mtime,
            status=status
        )
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        return asset

    # --- JOB QUEUE OPERATIONEN ---

    async def create_job(
        self,
        job_id: UUID,
        asset_path: str,
        original_path: str,
        cloud_path: str,
        operation: OperationType,
    ) -> IngestionJobModel:
        """Erstellt einen neuen Ingestion-Job, verknüpft mit dem Asset Ledger (Foreign Key)."""
        job = IngestionJobModel(
            job_id=job_id,
            asset_path=asset_path,
            original_path=original_path,
            cloud_path=cloud_path,
            operation=operation,
            status=JobStatus.PENDING,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def fetch_next_pending_job_with_skip_locked(self) -> Optional[IngestionJobModel]:
        """
        Multi-Worker-Concurreny: Holt den nächsten Pending-Job und sperrt ihn 
        sofort atomar für andere Worker, ohne zu blockieren (SKIP LOCKED).
        """
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
