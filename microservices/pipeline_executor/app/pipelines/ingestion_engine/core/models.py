# applications/rag/ingestion_engine/core/models.py

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


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
    DELETED = "deleted"


# --- 1. CONFIG MODELL ---

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


# --- 2. SNAPSHOT MODELL (Flüchtiger Ist-Zustand im Speicher) ---

class FileSnapshot(BaseModel):
    path: Path = Field(..., description="Relativer oder absoluter Pfad der Datei als eindeutiger Identifier")
    size_bytes: int = Field(..., ge=0, description="Dateigröße in Bytes")
    mtime: datetime = Field(..., description="Letzte Modifikationszeit (UTC)")
    file_hash: Optional[str] = Field(
        None, description="Inhalts-Hash (z.B. xxhash/sha256) zur Kollisions- und Änderungsprüfung"
    )

    @field_validator("path", mode="before")
    @classmethod
    def ensure_path(cls, v):
        return Path(v) if v else v


# --- 3. ASSET REGISTRY MODELL (Das persistente Gedächtnis) ---

class AssetRecord(BaseModel):
    file_path: Path = Field(..., description="Eindeutiger Primärschlüssel (Dateipfad)")
    last_seen_hash: str = Field(..., description="Letzter bekannter Inhalts-Hash")
    last_seen_mtime: datetime = Field(..., description="Letzte bekannte Modifikationszeit")
    status: AssetStatus = Field(default=AssetStatus.PENDING, description="Aktueller Verarbeitungsstatus des Assets")
    last_error: Optional[str] = Field(None, description="Letzter Stacktrace/Fehler falls fehlgeschlagen")
    deleted_at: Optional[datetime] = Field(None, description="Zeitpunkt des Soft Deletes falls verwaist")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Letztes Update des Records")

    @field_validator("file_path", mode="before")
    @classmethod
    def ensure_path(cls, v):
        return Path(v) if v else v


# --- 4. JOBLIST (RECONCILIATION RESULT) MODELL ---

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
