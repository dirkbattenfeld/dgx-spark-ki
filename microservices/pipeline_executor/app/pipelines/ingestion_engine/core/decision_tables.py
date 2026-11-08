# pipeline_executor/app/pipelines/ingestion_engine/core/decision_tables.py

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List

from pipelines.ingestion_engine.core.models import (
    AssetStatus,
    DiffStatus,
    JobCommand,
    JobFieldDelta,
    JobStatus,
    LedgerFieldDelta,
    OperationType,
    PipelineCommand,
    PlannedAction,
)

logger = logging.getLogger(__name__)


class DecisionRule:
    def __init__(self, name: str, conditions: List[Callable[[Any], bool]], actions: Dict[str, Any]):
        self.name = name
        self.conditions = conditions
        self.actions = actions


class DecisionTableRunner:
    @staticmethod
    def evaluate(context: Any, rules: List[DecisionRule]) -> Any:
        for rule in rules:
            try:
                match = all(cond(context) for cond in rule.conditions)
                if match:
                    logger.debug("🎯 [Decision Table] Regel greift: %s", rule.name)
                    for key, value in rule.actions.items():
                        if callable(value):
                            # Für dynamische Mutationen (z.B. Lambdas die Dictionaries zurückgeben)
                            mutation_result = value(context)
                            setattr(context, key, mutation_result)
                        else:
                            setattr(context, key, value)
                    break
            except Exception as e:
                logger.error("❌ Fehler bei Auswertung von Regel '%s': %s", rule.name, e)
                raise
        return context


# Rules für Reconciler

STAGE_1_RULES = [
    DecisionRule(
        name="PathAndMtimeUnchanged",
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is not None and ctx.snapshot_item.mtime == ctx.ledger_record.last_success_mtime],
        actions={"active_command": PipelineCommand.NONE, "diff_status": DiffStatus.UNCHANGED, "planned_action": PlannedAction.SKIP}
    ),
    DecisionRule(
        name="TriggerHashComputation",
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.snapshot_item.file_hash is None],
        actions={"active_command": PipelineCommand.COMPUTE_HASH}
    ),
    DecisionRule(
        name="FileDeleted_Synced",
        conditions=[
            lambda ctx: ctx.snapshot_item is None and ctx.ledger_record is not None and ctx.ledger_record.status == AssetStatus.SYNCED
        ],
        actions={"active_command": PipelineCommand.NONE, "diff_status": DiffStatus.DELETED, "planned_action": PlannedAction.REMOVE_VECTORS}
    ),
    DecisionRule(
        name="FileDeleted_PendingGhost",
        conditions=[
            lambda ctx: ctx.snapshot_item is None and ctx.ledger_record is not None and ctx.ledger_record.status == AssetStatus.PENDING
        ],
        actions={"active_command": PipelineCommand.NONE, "diff_status": DiffStatus.DELETED, "planned_action": PlannedAction.CANCEL_PENDING_CREATE}
    ),
]


STAGE_2_RULES = [
    DecisionRule(
        name="PassThroughIfSkipOrDeleted",
        conditions=[lambda ctx: ctx.planned_action in [PlannedAction.SKIP, PlannedAction.REMOVE_VECTORS, PlannedAction.CANCEL_PENDING_CREATE]],
        actions={}
    ),
    DecisionRule(
        name="FileIsSyncedFalseAlarm",
        # BEGRÜNDUNG: Der Zeitstempel (mtime) hat sich zwar geändert, aber der berechnete Hash 
        # ist identisch mit dem Ledger-Hash. Das fängt False Alarms (z. B. durch Backups oder Kopiervorgänge) 
        # ab und verhindert unnötiges Re-Parsing. Führt nur ein mtime-Update aus (SYNCED).
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is not None and ctx.snapshot_item.file_hash == ctx.ledger_record.last_success_hash],
        actions={"diff_status": DiffStatus.UNCHANGED, "planned_action": PlannedAction.SYNCED}
    ),
    DecisionRule(
        name="FileIsTrulyNew",
        # BEGRÜNDUNG: Die Datei existiert im Ledger noch überhaupt nicht (völlig neuer Pfad) 
        # -> Volles Indexieren (INDEX_FULL / Create).
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is None],
        actions={"diff_status": DiffStatus.NEW,
                 "planned_action": PlannedAction.INDEX_NEW,
                 "active_command": PipelineCommand.UPLOAD_S3
        }
    ),
    DecisionRule(
        name="FileIsModifiedInPlace",
        # BEGRÜNDUNG: Die Datei existiert im Ledger, aber der Hash weicht ab (Inhalt wurde tatsächlich editiert) 
        # -> Volles Neu-Indexieren (INDEX_FULL / Update).
        conditions=[
            lambda ctx: ctx.snapshot_item is not None 
            and ctx.ledger_record is not None 
            and ctx.snapshot_item.file_hash is not None 
            and ctx.snapshot_item.file_hash != ctx.ledger_record.last_success_hash
        ],
        actions={"diff_status": DiffStatus.MODIFIED,
                 "planned_action": PlannedAction.INDEX_MODIFIED,
                 "active_command": PipelineCommand.UPLOAD_S3
        }
    )   
]


STAGE_3_RULES = [
    # Fängt ab, wenn der S3-Upload in der Shell bei neuer Datei fehlgeschlagen ist
    DecisionRule(
        name="PrepUploadFailedNew",
        conditions=[lambda ctx: ctx.upload_error is not None and ctx.planned_action == PlannedAction.INDEX_NEW],
        actions={
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=str(ctx.path),
                delta_operation="insert", 
                status=AssetStatus.FAILED,
                last_error=ctx.upload_error
            ),
            "job_mutation": None  
        }
    ),
    # Fängt ab, wenn der S3-Upload in der Shell bei Dateiupdate fehlgeschlagen ist
    DecisionRule(
        name="PrepUploadFailedModified",
        conditions=[lambda ctx: ctx.upload_error is not None and ctx.planned_action == PlannedAction.INDEX_MODIFIED],
        actions={
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=str(ctx.path),
                delta_operation="update_strict",
                status=AssetStatus.FAILED,
                last_error=ctx.upload_error
            ),
            "job_mutation": None  
        }
    ),
    DecisionRule(
        name="PrepFullIndexNew",
        conditions=[
            lambda ctx: ctx.planned_action == PlannedAction.INDEX_NEW],
        actions={
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=str(ctx.path),
                delta_operation="insert",
                status=AssetStatus.PENDING
            ),
            "job_mutation": lambda ctx: JobFieldDelta(
                asset_path=str(ctx.path),
                original_path=ctx.snapshot_item.path,
                cloud_path=ctx.s3_path,
                operation=OperationType.CREATE,
                delta_operation="insert",
                status=JobStatus.PENDING,
                target_hash=ctx.snapshot_item.file_hash,
                target_mtime=ctx.snapshot_item.mtime
            )
        }
    ),
    DecisionRule(
        name="PrepFullIndexModified",
        conditions=[
            lambda ctx: ctx.planned_action == PlannedAction.INDEX_MODIFIED],
        actions={
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=str(ctx.path),
                delta_operation="update_strict",
                status=AssetStatus.PENDING 
            ),
            "job_mutation": lambda ctx: JobFieldDelta(
                asset_path=str(ctx.path),
                original_path=ctx.snapshot_item.path,
                cloud_path=ctx.s3_path,
                operation=OperationType.UPDATE,
                delta_operation="insert",
                status=JobStatus.PENDING,
                target_hash=ctx.snapshot_item.file_hash,
                target_mtime=ctx.snapshot_item.mtime
            )
        }
    ),
    DecisionRule(
        name="PrepSynced",
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.SYNCED],
        actions={
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=str(ctx.path),
                delta_operation="update_strict",
                status=AssetStatus.SYNCED,
                last_success_mtime=ctx.snapshot_item.mtime
            ),
            "job_mutation": None
        }
    ),
    DecisionRule(
        name="PrepDeletion",
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.REMOVE_VECTORS],
        actions={
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=str(ctx.path),
                delta_operation="update_strict",
                status=AssetStatus.PENDING
            ),
            "job_mutation": lambda ctx: JobFieldDelta(
                asset_path=str(ctx.path),
                original_path=Path(ctx.path),
                cloud_path="",
                operation=OperationType.DELETE,
                delta_operation="insert",
                status=JobStatus.PENDING
            )
        }
    ),
    DecisionRule(
        name="PrepSkipNoMutation",
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.SKIP],
        actions={
            "ledger_mutation": None,
            "job_mutation": None
        }
    ),
    DecisionRule(
        name="PrepCancelPendingCreate",
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.CANCEL_PENDING_CREATE],
        actions={
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=str(ctx.path),
                delta_operation="delete"
            ),
            "job_mutation": lambda ctx: JobFieldDelta(
                asset_path=str(ctx.path),
                original_path=Path(ctx.path),
                cloud_path="",
                operation=OperationType.DELETE,
                delta_operation="delete"  # Löscht die Pending-Jobs über das Repo
            )
        }
    ),
]


# Rules für Worker
# STAGE 1: Payload ausführen
WORKER_STAGE_1_RULES = [
    DecisionRule(
        name="TriggerPayloadExecution",
        conditions=[lambda ctx: ctx.job.status == JobStatus.RUNNING and ctx.execution_error is None],
        actions={"active_command": JobCommand.EXECUTE_PAYLOAD}
    )
]

# STAGE 2: Post-Execution Weiche (Fehler-Analyse ODER direkter Erfolg)
WORKER_STAGE_2_RULES = [
    DecisionRule(
        name="Path_HasError",
        conditions=[lambda ctx: ctx.execution_error is not None],
        actions={
            "active_command": JobCommand.ANALYZE_ERROR,
            "error_classified": True,
            "error_severity": "error"
        }
    ),
    DecisionRule(
        name="Path_Success_CreateOrUpdate",
        conditions=[lambda ctx: ctx.execution_error is None and ctx.job.operation in {OperationType.CREATE, OperationType.UPDATE}],
        actions={
            "active_command": JobCommand.NONE,
            "error_classified": True,
            "error_severity": "none",
            "new_job_status": JobStatus.SUCCESS,
            "increment_retry": False,
            # ERST HIER SCHREIBEN WIR MTIME UND HASH IN DEN LEDGER!
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=ctx.job.asset_path,
                delta_operation="update_strict",
                status=AssetStatus.SYNCED,
                last_success_hash=ctx.job.target_hash,
                last_success_mtime=ctx.job.target_mtime
            )
        }
    ),
    DecisionRule(
        name="Path_Success_Delete",
        conditions=[lambda ctx: ctx.execution_error is None and ctx.job.operation == OperationType.DELETE],
        actions={
            "active_command": JobCommand.NONE,
            "error_classified": True,
            "error_severity": "none",
            "new_job_status": JobStatus.SUCCESS,
            "increment_retry": False,
            # ERST WENN DER WORKER FERTIG IST (Vektoren gelöscht etc.), 
            # wird das Asset final aus der Registry entfernt!
            "ledger_mutation": lambda ctx: LedgerFieldDelta(
                file_path=ctx.job.asset_path,
                delta_operation="delete",
            )
        }
    )
]

# STAGE 3: Nur für den Fehlerfall: Retry vs. DeadLetter Entscheidung
WORKER_STAGE_3_RULES = [
    DecisionRule(
        name="Error_Retry",
        conditions=[
            lambda ctx: ctx.execution_error is not None and (ctx.job.retry_count + 1) < ctx.job.max_retries
        ],
        actions={
            "active_command": JobCommand.NONE,
            "new_job_status": JobStatus.PENDING,
            "increment_retry": True
        }
    ),
    DecisionRule(
        name="Error_DeadLetter",
        conditions=[
            lambda ctx: ctx.execution_error is not None and (ctx.job.retry_count + 1) >= ctx.job.max_retries
        ],
        actions={
            "active_command": JobCommand.NONE,
            "new_job_status": JobStatus.DEAD_LETTER,
            "increment_retry": True
        }
    ),
    DecisionRule(
        name="Success_PassThrough",
        conditions=[lambda ctx: ctx.execution_error is None],
        actions={}
    )
]


