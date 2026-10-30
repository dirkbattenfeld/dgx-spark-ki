# pipeline_executor/app/pipelines/ingestion_engine/core/decision_tables.py

import logging
from typing import Any, Callable, Dict, List

from pipelines.ingestion_engine.core.models import (
    AssetContext,
    AssetStatus,
    DiffStatus,
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
            match = all(cond(context) for cond in rule.conditions)
            if match:
                logger.debug("📋 Decision Rule angewendet: '%s'", rule.name)
                for key, val in rule.actions.items():
                    if callable(val):
                        setattr(context, key, val(context))
                    else:
                        setattr(context, key, val)
                break
        return context


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
        name="HashComputedMatches",
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is not None and ctx.snapshot_item.file_hash == ctx.ledger_record.last_seen_hash],
        actions={"active_command": PipelineCommand.NONE, "diff_status": DiffStatus.UNCHANGED, "planned_action": PlannedAction.SKIP}
    ),
    DecisionRule(
        name="HashComputedDiffers",
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is not None and ctx.snapshot_item.file_hash != ctx.ledger_record.last_seen_hash],
        actions={"active_command": PipelineCommand.DETECT_MOVE}
    ),
    DecisionRule(
        name="NewFileDetectMove",
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is None],
        actions={"active_command": PipelineCommand.DETECT_MOVE}
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
        name="FileIsMoved",
        conditions=[lambda ctx: ctx.detected_old_path is not None],
        actions={"diff_status": DiffStatus.MOVED, "planned_action": PlannedAction.UPDATE_PATH_ONLY}
    ),
    DecisionRule(
        name="FileIsTrulyNew",
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is None and ctx.detected_old_path is None],
        actions={"diff_status": DiffStatus.NEW, "planned_action": PlannedAction.INDEX_FULL}
    ),
    DecisionRule(
        name="FileIsModifiedInPlace",
        conditions=[lambda ctx: ctx.snapshot_item is not None and ctx.ledger_record is not None and ctx.snapshot_item.file_hash != ctx.ledger_record.last_seen_hash and ctx.detected_old_path is None],
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
        name="PrepMove",
        conditions=[lambda ctx: ctx.planned_action == PlannedAction.UPDATE_PATH_ONLY],
        actions={
            "ledger_mutation": lambda ctx: {"action": "move", "old_path": ctx.detected_old_path, "new_path": ctx.detected_new_path}
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


WORKER_STAGE_1_RULES = [
    DecisionRule(
        name="HasError",
        conditions=[lambda ctx: ctx.execution_error is not None],
        actions={"error_classified": True, "error_severity": "error"}
    ),
    DecisionRule(
        name="NoError",
        conditions=[lambda ctx: ctx.execution_error is None],
        actions={"error_classified": True, "error_severity": "none"}
    ),
]

WORKER_STAGE_2_RULES = [
    DecisionRule(
        name="Success",
        conditions=[lambda ctx: ctx.execution_error is None],
        actions={"new_job_status": JobStatus.SUCCESS, "increment_retry": False}
    ),
    DecisionRule(
        name="Retry",
        conditions=[lambda ctx: ctx.execution_error is not None and ctx.job.retry_count + 1 < ctx.job.max_retries],
        actions={"new_job_status": JobStatus.PENDING, "increment_retry": True}
    ),
    DecisionRule(
        name="DeadLetter",
        conditions=[lambda ctx: ctx.execution_error is not None and ctx.job.retry_count + 1 >= ctx.job.max_retries],
        actions={"new_job_status": JobStatus.DEAD_LETTER, "increment_retry": True}
    ),
]
