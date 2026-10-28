# /pipeline_executor/app/pipelines/ingestion_engine/db/models.py

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, MetaData, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Importiere deine Enums aus den Pydantic-Modellen
from pipelines.ingestion_engine.core.models import (
    AssetStatus,
    JobStatus,
    OperationType,
)

# WICHTIG: Naming Convention definiert feste Regeln für Constraint- und Indesnamen.
# Das verhindert Alembic-Warnungen und unbenannte drop_constraint(None)-Fehler.
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


class AssetRecordModel(Base):
    __tablename__ = "asset_registry"

    # Primärschlüssel als String (Pfad)
    file_path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    last_seen_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    last_seen_mtime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[AssetStatus] = mapped_column(
        SQLEnum(AssetStatus, name="asset_status_enum"),
        default=AssetStatus.PENDING,
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    # Performance-Index für Hash-Lookups (für Rename / Move Detection)
    __table_args__ = (
        Index("idx_asset_hash_lookup", "last_seen_hash"),
    )

    def to_path(self) -> Path:
        return Path(self.file_path)


class IngestionJobModel(Base):
    __tablename__ = "ingestion_jobs"

    job_id: Mapped[UUID] = mapped_column(primary_key=True)
    
    # Harten Foreign Key auf das Asset Ledger (file_path) setzen
    asset_path: Mapped[str] = mapped_column(
        String(1024), 
        ForeignKey("asset_registry.file_path", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )

    original_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    cloud_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    operation: Mapped[OperationType] = mapped_column(
        SQLEnum(OperationType, name="operation_type_enum"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, name="job_status_enum"),
        default=JobStatus.PENDING,
        index=True,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    stacktrace: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    # WICHTIG: Zusammengesetzter Index für das SKIP LOCKED Worker-Pattern
    __table_args__ = (
        Index("idx_jobs_status_created", "status", "created_at"),
    )
