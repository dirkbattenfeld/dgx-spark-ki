# pipelines/ingestion_engine/db/repository.py

from collections.abc import Sequence
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipelines.ingestion_engine.db.models import (
    AssetRegistry,
    AssetStatus,
    IngestionJob,
    JobStatus,
)


class AssetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_hash(self, file_hash: str) -> Optional[AssetRegistry]:
        """Sucht ein Asset anhand seines SHA-256 Hashes (wichtig für Deduplizierung)."""
        result = await self.session.execute(
            select(AssetRegistry).where(AssetRegistry.last_seen_hash == file_hash)
        )
        return result.scalars().first()

    async def create(
        self, 
        file_path: str, 
        last_seen_hash: str, 
        file_size: int, 
        status: AssetStatus = AssetStatus.PENDING
    ) -> AssetRegistry:
        """Legt einen neuen Asset-Eintrag im Ledger an."""
        asset = AssetRegistry(
            file_path=file_path,
            last_seen_hash=last_seen_hash,
            file_size=file_size,
            status=status
        )
        self.session.add(asset)
        # Wir flushen hier, damit die DB die ID generiert, ohne die Transaktion direkt zu committen
        await self.session.flush()
        await self.session.refresh(asset)
        return asset