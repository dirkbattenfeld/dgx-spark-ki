# applications/rag/ingestion_engine/config/schema.py

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field, field_validator


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
