# pipeline_executor/app/pipelines/ingestion_engine/services/reconciler.py

import logging
from typing import Dict, List, Set

from storage.client import StorageClient

from pipelines.ingestion_engine.core.config import settings
from pipelines.ingestion_engine.core.decision_tables import (
    STAGE_1_RULES,
    STAGE_2_RULES,
    STAGE_3_RULES,
    DecisionTableRunner,
)
from pipelines.ingestion_engine.core.models import (
    AssetContext,
    FileSnapshot,
    PipelineCommand,
)
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork
from pipelines.ingestion_engine.services.effect_handlers import (
    PIPELINE_EFFECT_REGISTRY,
    EffectExecutionRunner,
)

logger = logging.getLogger(__name__)


class ReconciliationService:
    def __init__(self, uow: AsyncUnitOfWork, storage_client: StorageClient):
        self.uow = uow
        self.storage = storage_client
        self.batch_size = settings.ingestion_batch_size

    async def reconcile(self, snapshots: List[FileSnapshot]) -> int:
        logger.info("🔄 Starte Chunked Reconciler (Batchgröße: %d, Total Snapshots: %d)", self.batch_size, len(snapshots))
        
        snapshot_map = {str(s.path): s for s in snapshots}

        async with self.uow as uow:
            db_assets = await uow.repo.get_active_assets()
            ledger_map = {asset.file_path: asset for asset in db_assets}

        all_paths = sorted(list(set(snapshot_map.keys()) | set(ledger_map.keys())))
        total_processed = 0

        for i in range(0, len(all_paths), self.batch_size):
            chunk_paths = all_paths[i : i + self.batch_size]
            logger.info("📦 Verarbeite Transaktions-Chunk %d bis %d von %d...", i, i + len(chunk_paths), len(all_paths))

            ledger_mutations = []
            job_mutations = []
            vector_operations = []

            async with self.uow as chunk_uow:
                for path in chunk_paths:
                    snap = snapshot_map.get(path)
                    ledger = ledger_map.get(path)

                    ctx = AssetContext(path=path, snapshot_item=snap, ledger_record=ledger)

                    # Stage 1
                    ctx = DecisionTableRunner.evaluate(ctx, STAGE_1_RULES)
                    await EffectExecutionRunner.execute_command(ctx, PIPELINE_EFFECT_REGISTRY, chunk_uow, self.storage)
                    if ctx.active_command != PipelineCommand.NONE:
                        ctx = DecisionTableRunner.evaluate(ctx, STAGE_1_RULES)

                    # Stage 2
                    ctx = DecisionTableRunner.evaluate(ctx, STAGE_2_RULES)
                    await EffectExecutionRunner.execute_command(ctx, PIPELINE_EFFECT_REGISTRY, chunk_uow, self.storage)
                    ctx = DecisionTableRunner.evaluate(ctx, STAGE_2_RULES)

                    # Stage 3
                    ctx = DecisionTableRunner.evaluate(ctx, STAGE_3_RULES)
                    if ctx.ledger_mutation:
                        ledger_mutations.append(ctx.ledger_mutation)
                    if ctx.job_mutation:
                        job_mutations.append(ctx.job_mutation)
                    if ctx.vector_operation:
                        vector_operations.append(ctx.vector_operation)

                    total_processed += 1

                # Bulk-Persistenz für diesen Chunk
                if ledger_mutations or job_mutations or vector_operations:
                    await chunk_uow.repo.bulk_persist_chunk(ledger_mutations, job_mutations, vector_operations)

        logger.info("✨ Chunked Reconciler beendet. Total verarbeitet: %d", total_processed)
        return total_processed
    