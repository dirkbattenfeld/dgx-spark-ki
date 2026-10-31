# pipeline_executor/app/pipelines/ingestion_engine/core/decision_tables.py

import logging
from typing import Any, Callable, Dict, List

from pipelines.ingestion_engine.core.models import (
    AssetContext,
    AssetStatus,
    DiffStatus,
    JobCommand,
    JobStatus,
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
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is not None and ctx.snapshot_item.mtime == ctx.ledger_record.last_seen_mtime],
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
        name="FileIsSyncedFalseAlarm",
        # BEGRÜNDUNG: Der Zeitstempel (mtime) hat sich zwar geändert, aber der berechnete Hash 
        # ist identisch mit dem Ledger-Hash. Das fängt False Alarms (z. B. durch Backups oder Kopiervorgänge) 
        # ab und verhindert unnötiges Re-Parsing. Führt nur ein mtime-Update aus (SYNCED).
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is not None and ctx.snapshot_item.file_hash == ctx.ledger_record.last_seen_hash],
        actions={"diff_status": DiffStatus.UNCHANGED, "planned_action": PlannedAction.SYNCED}
    ),
    DecisionRule(
        name="FileIsTrulyNew",
        # BEGRÜNDUNG: Die Datei existiert im Ledger noch überhaupt nicht (völlig neuer Pfad) 
        # -> Volles Indexieren (INDEX_FULL / Create).
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is None],
        actions={"diff_status": DiffStatus.NEW, "planned_action": PlannedAction.INDEX_FULL}
    ),
    DecisionRule(
        name="FileIsModifiedInPlace",
        # BEGRÜNDUNG: Die Datei existiert im Ledger, aber der Hash weicht ab (Inhalt wurde tatsächlich editiert) 
        # -> Volles Neu-Indexieren (INDEX_FULL / Update).
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is not None and ctx.snapshot_item.file_hash != ctx.ledger_record.last_seen_hash],
        actions={"diff_status": DiffStatus.MODIFIED, "planned_action": PlannedAction.INDEX_FULL}
    ),
    DecisionRule(
        name="PassThroughIfSkipOrDeleted",
        conditions=[lambda ctx: ctx.planned_action in [PlannedAction.SKIP, PlannedAction.REMOVE_VECTORS]],
        actions={}
    ),
]


STAGE_3_RULES = [
    DecisionRule(
        name="PrepFullIndex",
        # Greift nur, wenn ein gültiger Hash vorliegt (Neu oder Modifiziert)
        conditions=[
            lambda ctx: ctx.planned_action == PlannedAction.INDEX_FULL and ctx.snapshot_item is not None and ctx.snapshot_item.file_hash is not None
        ],
        actions={
            "ledger_mutation": lambda ctx: {"action": "upsert", "file_path": ctx.path, "hash": ctx.snapshot_item.file_hash, "mtime": ctx.snapshot_item.mtime},
            "job_mutation": lambda ctx: {"operation": "create", "asset_path": ctx.path, "cloud_path": f"s3://staging/{ctx.path}"}
        }
    ),
    DecisionRule(
        name="PrepSynced",
        # BEGRÜNDUNG: Aktualisiert bei inhaltsgleichen Dateien (False Alarm) lediglich den mtime-Zeitstempel 
        # im Ledger. Es werden keine Jobs oder Vektor-Operationen generiert.
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.SYNCED and ctx.snapshot_item is not None],
        actions={
            "ledger_mutation": lambda ctx: {"action": "update_mtime", "file_path": ctx.path, "mtime": ctx.snapshot_item.mtime},
            "job_mutation": None,
            "vector_operation": None
        }
    ),
    DecisionRule(
        name="PrepDeletion",
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.REMOVE_VECTORS],
        actions={
            "ledger_mutation": lambda ctx: {"action": "delete", "file_path": ctx.path},
            "vector_operation": lambda ctx: {"action": "delete_by_path", "path": ctx.path},
            "job_mutation": lambda ctx: {"operation": "delete", "asset_path": ctx.path, "cloud_path": ""}
        }
    ),
    DecisionRule(
        name="PrepSkipNoMutation",
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.SKIP],
        actions={
            "ledger_mutation": None,
            "job_mutation": None,
            "vector_operation": None
        }
    ),
    DecisionRule(
        name="PrepCancelPendingCreate",
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.CANCEL_PENDING_CREATE],
        actions={
            "ledger_mutation": lambda ctx: {"action": "cancel_pending", "file_path": ctx.path},
            "job_mutation": None,
            "vector_operation": None
        }
    ),
]


# Rules für Worker
# STAGE 1: Payload ausführen
WORKER_STAGE_1_RULES = [
    DecisionRule(
        name="TriggerPayloadExecution",
        conditions=[lambda ctx: ctx.job.status == JobStatus.PENDING and ctx.execution_error is None],
        actions={"active_command": JobCommand.EXECUTE_PAYLOAD}
    )
]

# STAGE 2: Post-Execution Weiche (Fehler-Analyse ODER direkter Erfolg)
WORKER_STAGE_2_RULES = [
    # Wenn ein Fehler aufgetreten ist -> Fehler analysieren
    DecisionRule(
        name="Path_HasError",
        conditions=[lambda ctx: ctx.execution_error is not None],
        actions={
            "active_command": JobCommand.ANALYZE_ERROR,
            "error_classified": True,
            "error_severity": "error"
        }
    ),
    # Wenn KEIN Fehler aufgetreten ist -> Direkt auf Erfolg stellen (Keine Analyse!)
    DecisionRule(
        name="Path_Success",
        conditions=[lambda ctx: ctx.execution_error is None],
        actions={
            "active_command": JobCommand.NONE,
            "error_classified": True,
            "error_severity": "none",
            "new_job_status": JobStatus.SUCCESS,
            "increment_retry": False
        }
    ),
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


