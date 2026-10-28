# pipeline_executor/app/pipelines/ingestion_engine/db/uow.py

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Importiere das zentrale Repository aus der repository.py
from pipelines.ingestion_engine.db.repository import IngestionRepository


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
