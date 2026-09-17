# applications/rag/ingestion_engine/core/models.py

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
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


# --- SNAPSHOT MODELL ---

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


# --- JOBLIST (DIFF RESULT) MODELL ---

class IngestionJob(BaseModel):
    job_id: UUID = Field(default_factory=uuid4, description="Eindeutige Job-ID (UUIDv4)")
    original_path: Path = Field(..., description="Quellpfad der Datei")
    cloud_path: str = Field(..., description="Zielpfad (S3-URI s3://bucket/path oder lokaler Zielpfad)")
    operation: OperationType = Field(..., description="Art der Operation (create, update, delete)")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Aktueller Verarbeitungsstatus")
    retry_count: int = Field(default=0, ge=0, description="Aktuelle Anzahl der Fehlversuche")
    max_retries: int = Field(default=3, ge=0, description="Maximale Anzahl an Retries vor Dead-Letter")
    stacktrace: Optional[str] = Field(None, description="Fehlermeldung / Stacktrace bei Fehlschlag")
    error_code: Optional[str] = Field(None, description="Maschinenlesbarer Fehlercode")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Erstellungszeitpunkt des Jobs")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Letztes Update des Job-Status")

    @field_validator("original_path", mode="before")
    @classmethod
    def ensure_path(cls, v):
        return Path(v) if v else v
