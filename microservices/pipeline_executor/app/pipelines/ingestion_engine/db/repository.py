# pipeline_executor/app/pipelines/ingestion_engine/db/repository.py

import logging
from datetime import datetime, timezone
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
