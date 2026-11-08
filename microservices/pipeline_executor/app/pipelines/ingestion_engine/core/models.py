# pipeline_executor/app/pipelines/ingestion_engine/core/models.py

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"

class OperationType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
 
class AssetStatus(str, Enum):
    SYNCED = "synced"
    PENDING = "pending"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"

class DiffStatus(str, Enum):
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    NEW = "NEW"
    DELETED = "DELETED"
    
class PlannedAction(str, Enum):
    SKIP = "SKIP"
    INDEX_NEW = "INDEX_NEW"
    INDEX_MODIFIED = "INDEX_MODIFIED"
    REMOVE_VECTORS = "REMOVE_VECTORS"
    CANCEL_PENDING_CREATE = "CANCEL_PENDING_CREATE"
    SYNCED = "synced"

class PipelineCommand(str, Enum):
    NONE = "NONE"
    COMPUTE_HASH = "COMPUTE_HASH"
    UPLOAD_S3 = "UPLOAD_S3"
 
class JobCommand(str, Enum):
    NONE = "NONE"
    EXECUTE_PAYLOAD = "EXECUTE_PAYLOAD"
    ANALYZE_ERROR = "ANALYZE_ERROR"
    PERSIST_RESULT = "PERSIST_RESULT"
    
    
# --- CONFIG MODELL ---
class PathRuleConfig(BaseModel):
    path: Path
    exclude_paths: List[Path] = Field(default_factory=list, description="Vollständige Pfade oder Unterpfade die ignoriert werden")
    exclude_extensions: List[str] = Field(default_factory=list, description="Pfadspezifische Dateiendungen zum Ausschließen")

    @field_validator("path", "exclude_paths", mode="before")
    @classmethod
    def ensure_path(cls, v):
        return Path(v) if v else v


class PipelineConfig(BaseModel):
    global_allowed_extensions: List[str] = Field(
        ..., description="Global erlaubte Dateiendungen (z. B. .pdf, .docx, .md)"
    )
    watched_targets: List[PathRuleConfig] = Field(
        ..., description="Liste der zu überwachenden Quellpfade mit ihren Regeln"
    )


# --- SNAPSHOT MODELL (Flüchtiger Ist-Zustand im Speicher) ---

class FileSnapshot(BaseModel):
    path: Path = Field(..., description="Relativer oder absoluter Pfad der Datei als eindeutiger Identifier")
#    size_bytes: int = Field(..., ge=0, description="Dateigröße in Bytes")
    mtime: datetime = Field(..., description="Letzte Modifikationszeit (UTC)")
    file_hash: Optional[str] = Field(
        None, description="Inhalts-Hash (z.B. xxhash/sha256) zur Kollisions- und Änderungsprüfung"
    )

    @field_validator("path", mode="before")
    @classmethod
    def ensure_path(cls, v):
        return Path(v) if v else v


# --- ASSET REGISTRY MODELL (Das persistente Gedächtnis) ---

class AssetRecord(BaseModel):
    file_path: Path = Field(..., description="Eindeutiger Primärschlüssel (Dateipfad)")
    last_success_hash: str = Field(..., description="Letzter bekannter Inhalts-Hash")
    last_success_mtime: datetime = Field(..., description="Letzte bekannte Modifikationszeit")
    status: AssetStatus = Field(default=AssetStatus.PENDING, description="Aktueller Verarbeitungsstatus des Assets")
    last_error: Optional[str] = Field(None, description="Letzter Stacktrace/Fehler falls fehlgeschlagen")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Letztes Update des Records")

    @field_validator("file_path", mode="before")
    @classmethod
    def ensure_path(cls, v):
        return Path(v) if v else v
    
    model_config = ConfigDict(from_attributes=True)


# --- JOBLIST (RECONCILIATION RESULT) MODELL ---

class IngestionJob(BaseModel):
    job_id: UUID = Field(default_factory=uuid4, description="Eindeutige Job-ID (UUIDv4)")
    asset_id: Optional[UUID] = Field(None, description="Fremdschlüssel zur verknüpften Asset Registry")
    original_path: Path = Field(..., description="Quellpfad der Datei")
    cloud_path: str = Field(..., description="Zielpfad (S3-URI s3://bucket/path oder lokaler Zielpfad)")
    operation: OperationType = Field(..., description="Art der Operation (create, update, delete)")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Aktueller Verarbeitungsstatus")
    retry_count: int = Field(default=0, ge=0, description="Aktuelle Anzahl der Fehlversuche")
    max_retries: int = Field(default=3, ge=0, description="Maximale Anzahl an Retries vor Dead-Letter")
    stacktrace: Optional[str] = Field(None, description="Fehlermeldung / Stacktrace bei Fehlschlag")
    error_code: Optional[str] = Field(None, description="Maschinenlesbarer Fehlercode")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Erstellungszeitpunkt des Jobs")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Letztes Update des Job-Status")

    @field_validator("original_path", mode="before")
    @classmethod
    def ensure_path(cls, v):
        return Path(v) if v else v


# --- DELTA MODELLE (Reine Änderungs-Pakete vom Core zur Shell) ---

class LedgerFieldDelta(BaseModel):
    file_path: str
    delta_operation: Literal["insert", "update_strict", "delete"]
    
    # Optional gehalten: Nur gesetzte Felder (nicht-None) werden geschrieben
    status: Optional[AssetStatus] = None
    last_success_hash: Optional[str] = None
    last_success_mtime: Optional[datetime] = None
    last_error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobFieldDelta(BaseModel):
    job_id: Optional[UUID] = Field(default_factory=uuid4)
    asset_path: str
    original_path: Path
    cloud_path: str
    operation: OperationType
    delta_operation: Literal["insert", "update_strict", "delete"] = "insert"
    
    status: Optional[JobStatus] = None
    retry_count: Optional[int] = None
    stacktrace: Optional[str] = None
    
    # Die mitgeschleiften Werte für die spätere Ledger-Aktualisierung durch den Worker
    target_hash: Optional[str] = None
    target_mtime: Optional[datetime] = None

    @field_validator("original_path", mode="before")
    @classmethod
    def ensure_path(cls, v):
        return Path(v) if v else v

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


# --- PIPELINE CONTEXT ---
class AssetContext(BaseModel):
    path: str
    snapshot_item: Optional[FileSnapshot] = None
    ledger_record: Optional[AssetRecord] = None

    active_command: PipelineCommand = PipelineCommand.NONE
    diff_status: Optional[DiffStatus] = None
    planned_action: Optional[PlannedAction] = None

    # S3 upload
    upload_error: Optional[str] = None
    s3_path: Optional[str] = None
    
    # Typsichere Deltas anstelle von losen Dicts:
    ledger_mutation: Optional[LedgerFieldDelta] = None
    job_mutation: Optional[JobFieldDelta] = None
    

# --- JOB WORKER CONTEXT ---

class JobContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)
    
    job: Any  
    active_command: Optional[JobCommand] = None  
    execution_error: Optional[Exception] = None
    error_message: Optional[str] = None
    error_classified: bool = False
    error_severity: Optional[str] = None    
    new_job_status: Optional[Any] = None
    increment_retry: bool = False
    
    ledger_mutation: Optional[LedgerFieldDelta] = None