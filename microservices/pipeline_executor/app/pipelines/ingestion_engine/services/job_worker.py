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
from pipelines.ingestion_engine.services.effect_handlers import (
    WORKER_EFFECT_REGISTRY,
    EffectExecutionRunner,
)

logger = logging.getLogger(__name__)


async def run_job_worker_loop(uow_factory) -> int:
    processed = 0
    logger.info("⚙️ Starte Job Worker mit isolierten Transaktionsgrenzen...")

    # --- STARTUP CLEANUP: Verhindert Zombie-Jobs nach Testabbrüchen (über Repository gekapselt) ---
    async with uow_factory() as cleanup_uow:
        rowcount = await cleanup_uow.repo.reset_running_jobs_to_pending()
        logger.info("🧹 Startup Cleanup: %d hängengebliebene RUNNING-Jobs auf PENDING zurückgesetzt.", rowcount)

    while True:
        # --- TRANSAKTION A: Job holen & sperren ---
        async with uow_factory() as uow:
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
        await EffectExecutionRunner.execute_command(ctx, WORKER_EFFECT_REGISTRY)

        # --- TRANSAKTION B: Ergebnis isoliert persistieren ---
        async with uow_factory() as uow:
            target_job = await uow.session.get(IngestionJobModel, job_id)
            if target_job:
                target_job.status = ctx.new_job_status
                if ctx.increment_retry:
                    target_job.retry_count += 1
                if ctx.error_message:
                    target_job.stacktrace = ctx.error_message

        processed += 1

    logger.info("✨ Job Worker Loop beendet. Verarbeitete Jobs: %d", processed)
    return processed
