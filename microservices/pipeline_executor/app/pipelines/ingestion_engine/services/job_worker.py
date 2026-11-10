# pipeline_executor/app/pipelines/ingestion_engine/services/job_worker.py

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipelines.ingestion_engine.core.decision_tables import (
    WORKER_STAGE_1_RULES,
    WORKER_STAGE_2_RULES,
    WORKER_STAGE_3_RULES,
    DecisionTableRunner,
)
from pipelines.ingestion_engine.core.models import JobContext
from pipelines.ingestion_engine.db.uow import AsyncUnitOfWork
from pipelines.ingestion_engine.services.effect_handlers import (
    WORKER_EFFECT_REGISTRY,
    EffectExecutionRunner,
)

logger = logging.getLogger(__name__)

class JobWorkerService:
    def __init__(self, async_session_maker: async_sessionmaker[AsyncSession], max_concurrency: int = 2):
        self.async_session_maker = async_session_maker
        self.max_concurrency = max_concurrency

    async def run_worker_loop(self) -> int:
        logger.info("⚙️ Starte Job Worker Service mit %d parallelen Lanes...", self.max_concurrency)
            
        # --- WORKER-RESTART HOUSEKEEPING (Isolierte UoW für Cleanup) ---
        async with AsyncUnitOfWork(self.async_session_maker) as cleanup_uow:
            stats = await cleanup_uow.repo.worker_resume_housekeeping()
            logger.info(
                "🧹 Worker Housekeeping: %d Zombie-Jobs zu Pending zurückgesetzt | %d ins Dead-Letter verschoben.",
                stats["zombies_reset_to_pending"], stats["zombies_moved_to_dead_letter"]
            )
        
        # Spawne n parallele Worker-Coroutines
        worker_tasks = [
            self._worker_lane_loop(worker_id=i+1) 
            for i in range(self.max_concurrency)
        ]
        
        results = await asyncio.gather(*worker_tasks)
        total_processed = sum(results)

        logger.info("✨ Job Worker Pool beendet. Gesamte verarbeitete Jobs: %d", total_processed)
        return total_processed

    async def _worker_lane_loop(self, worker_id: int) -> int:
        """Einzelne Worker-Lane mit eigener, isolierter UoW-Instanz."""
        processed = 0
        logger.debug("👷 [Worker Lane %d] Gestartet und bereit für Jobs.", worker_id)

        while True:
            # --- TRANSAKTION A: Job holen & sperren (Frische UoW für diesen Fetch) ---
            uow_fetch = AsyncUnitOfWork(self.async_session_maker)
            async with uow_fetch as uow:
                job = await uow.repo.fetch_next_pending_job_with_skip_locked()
                if not job:
                    break
                job_id = job.job_id

            logger.info("👷 [Worker Lane %d] Hat Job übernommen: %s [Op: %s]", worker_id, job_id, job.operation)
            ctx = JobContext(job=job)
            
            try:
                # --- STAGE 1: Payload ausführen (Dokumenten-Parsing / gx10 Aufrufe) ---
                ctx = DecisionTableRunner.evaluate(ctx, WORKER_STAGE_1_RULES)
                await EffectExecutionRunner.execute_command(ctx, WORKER_EFFECT_REGISTRY)

                # --- STAGE 2: Post-Execution Weiche ---
                ctx = DecisionTableRunner.evaluate(ctx, WORKER_STAGE_2_RULES)
                await EffectExecutionRunner.execute_command(ctx, WORKER_EFFECT_REGISTRY)

                # --- STAGE 3: Retry vs. DeadLetter Entscheidung ---
                ctx = DecisionTableRunner.evaluate(ctx, WORKER_STAGE_3_RULES)

            except Exception as e:
                logger.error("❌ [Worker Lane %d] Unwarteter Fehler bei Job %s: %s", worker_id, job_id, e, exc_info=True)
                ctx.new_job_status = JobStatus.FAILED
                ctx.error_message = str(e)
                ctx.increment_retry = True

            # --- TRANSAKTION B: Atomare Persistenz (Frische UoW für den Commit) ---
            
            uow_persist = AsyncUnitOfWork(self.async_session_maker)
            async with uow_persist as persist_uow:
                await persist_uow.repo.apply_job_and_ledger_mutation(
                    job_id=job_id,
                    new_job_status=ctx.new_job_status,
                    increment_retry=ctx.increment_retry,
                    error_message=getattr(ctx, "error_message", None),
                    error_severity=getattr(ctx, "error_severity", None),
                    ledger_mutation=getattr(ctx, "ledger_mutation", None)
                )
 
            processed += 1

        logger.info("🏁 [Worker Lane %d] Beendet. Verarbeitete Jobs: %d", worker_id, processed)
        return processed


class JobWorkerService_alt:
    def __init__(self, uow: AsyncUnitOfWork):
        self.uow = uow

    async def run_worker_loop(self) -> int:
        logger.info("⚙️ Starte Job Worker Service mit isolierten Transaktionsgrenzen...")
            
        # --- WORKER-RESTART HOUSEKEEPING (Nur Zombie-Handling) ---
        async with self.uow as cleanup_uow:
            stats = await cleanup_uow.repo.worker_resume_housekeeping()
            logger.info(
                "🧹 Worker Housekeeping: %d Zombie-Jobs zu Pending zurückgesetzt | %d ins Dead-Letter verschoben.",
                stats["zombies_reset_to_pending"], stats["zombies_moved_to_dead_letter"]
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
                await persist_uow.repo.apply_job_and_ledger_mutation(
                    job_id=job_id,
                    new_job_status=ctx.new_job_status,
                    increment_retry=ctx.increment_retry,
                    error_message=ctx.error_message,
                    error_severity=getattr(ctx, "error_severity", None),
                    ledger_mutation=ctx.ledger_mutation  # <-- Das vom Worker-Decision-Table erzeugte Delta!
                )
 
            processed += 1

        logger.info("✨ Job Worker Loop beendet. Verarbeitete Jobs: %d", processed)
        return processed
