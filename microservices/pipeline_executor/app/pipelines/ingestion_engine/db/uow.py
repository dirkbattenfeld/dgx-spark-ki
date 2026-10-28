# pipeline_executor/app/pipelines/ingestion_engine/db/uow.py

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipelines.ingestion_engine.core.models import JobStatus
from pipelines.ingestion_engine.db.models import AssetRecordModel, IngestionJobModel


class IngestionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_asset_by_hash(self, file_hash: str) -> Optional[AssetRecordModel]:
        """Wird für die Rename-Detection genutzt: Existiert der Hash unter anderem Pfad?"""
        stmt = select(AssetRecordModel).where(AssetRecordModel.last_seen_hash == file_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def fetch_next_pending_job_with_skip_locked(self) -> Optional[IngestionJobModel]:
        """
        Der heilige Gral für Multi-Worker-Architekturen:
        Holt den nächsten Pending-Job und sperrt ihn sofort für andere Worker,
        ohne zu blockieren.
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


class AsyncUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.session: Optional[AsyncSession] = None
        self.repo: Optional[IngestionRepository] = None

    async def __aenter__(self):
        self.session = self.session_factory()
        self.repo = IngestionRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()
