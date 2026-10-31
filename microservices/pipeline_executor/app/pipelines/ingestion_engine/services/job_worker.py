# pipeline_executor/app/pipelines/ingestion_engine/services/job_worker.py

import logging

from pipelines.ingestion_engine.core.decision_tables import (
    WORKER_STAGE_1_RULES,
    WORKER_STAGE_2_RULES,
    WORKER_STAGE_3_RULES,
    DecisionTableRunner,
)
from pipelines.ingestion_engine.core.models import JobContext
from pipelines.ingestion_engine.db.models import IngestionJobModel
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork
from pipelines.ingestion_engine.services.effect_handlers import (
    WORKER_EFFECT_REGISTRY,
    EffectExecutionRunner,
)

logger = logging.getLogger(__name__)


class JobWorkerService:
    def __init__(self, uow: AsyncUnitOfWork):
        self.uow = uow

    async def run_worker_loop(self) -> int:
        logger.info("⚙️ Starte Job Worker Service mit isolierten Transaktionsgrenzen...")
            
        # --- STARTUP HOUSEKEEPING ---
        async with self.uow as cleanup_uow:
            zombie_count = await cleanup_uow.repo.reset_running_jobs_to_pending()
            pruned = await cleanup_uow.repo.prune_jobs()
            logger.info(
                "🧹 Startup Housekeeping: %d Zombie-Jobs zurückgesetzt | Pruned: %d Success, %d Dead-Letter.",
                zombie_count, pruned["pruned_success"], pruned["pruned_dead_letter"]
            )

        processed = 0

        while True:
            # --- TRANSAKTION A: Job holen & sperren ---
            async with self.uow as uow:
                job = await uow.repo.fetch_next_pending_job_with_skip_locked()
                if not job:
                    break
                job_id = job.job_id

            ctx = JobContext(job=job)

            # --- STAGE 1: Payload ausführen ---
            ctx = DecisionTableRunner.evaluate(ctx, WORKER_STAGE_1_RULES)
            await EffectExecutionRunner.execute_command(ctx, WORKER_EFFECT_REGISTRY)

            # --- STAGE 2: Post-Execution Weiche (Fehler-Analyse ODER direkter Erfolg) ---
            ctx = DecisionTableRunner.evaluate(ctx, WORKER_STAGE_2_RULES)
            await EffectExecutionRunner.execute_command(ctx, WORKER_EFFECT_REGISTRY)

            # --- STAGE 3: Nur im Fehlerfall: Retry vs. DeadLetter Entscheidung ---
            ctx = DecisionTableRunner.evaluate(ctx, WORKER_STAGE_3_RULES)

            # --- TRANSAKTION B: Atomare Persistenz (Job-Status + Asset Ledger Sync) ---
            async with self.uow as persist_uow:
                await persist_uow.repo.finalize_job_execution(
                    job_id=job_id,
                    new_job_status=ctx.new_job_status,
                    increment_retry=ctx.increment_retry,
                    error_message=ctx.error_message,
                    error_severity=getattr(ctx, "error_severity", None)
                )
 
            processed += 1

        logger.info("✨ Job Worker Loop beendet. Verarbeitete Jobs: %d", processed)
        return processed
