# ki/core/datapipeline/datapipeline_dataclasses.py

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Type, TypeVar, Generic 
from ki.bootstrap.infrasettings import InfraSettings

# GLOBAL BUILD CONTEXT
# Pipeline-weite, statische Infrastruktur, einmal beim Build gesetzt
@dataclass #(frozen=True)  # später wieder aktivieren, wenn komplett in main initialisiert
class GlobalBuildContext:
    component_registry: Any                 # ComponentRegistry
    prompt_factory: Optional[Any] = None  # optional, kann pro Pipeline einheitlich sein
    prompt_registry: Optional[Any] = None
    build_logger: Optional[logging.Logger] = None
    base_path: Path = None

# COMPONENT SPEC (Build, komponentenspezifisch)
# Statische Definition einer Komponente innerhalb der Pipeline
@dataclass(frozen=True)
class ComponentSpec:
    name: str                            
    cls: Type                            
    config_class: Optional[Type] = None   # CONFIG_CLASS der Komponente
    input_class: Optional[Type] = None    # INPUT_CLASS
    output_class: Optional[Type] = None   # OUTPUT_CLASS
    run_context_class: Optional[Type] = None    
    # Build-Zeit Parameter / Defaults
    build_config: Any = None

# GLOBAL RUN CONTEXT
# Pipeline-weite Parameter, die sich pro Run ändern können
@dataclass
class GlobalRunContext:
    run_id: int
    base_path: Path
    run_path: Path
    artifact_store: 'ArtifactStore'
    serializer_registry: 'serializer_registry'
    projector_registry: 'projektor_registry'
    flattener_registry: 'flattener_registry'
    writer_registry: 'writer_registry'
    infra: InfraSettings
    run_logger: Optional[logging.Logger] = None
    verbose: bool = False


TConfig = TypeVar("TConfig")

class BaseRunContext(Generic[TConfig]):
    def __init__(self, component_name: str, config: TConfig):
        self.component_name = component_name
        self.config = config
        self.modeltype_override: Optional[str] = None
        self.spec_override: Optional[dict] = None


from ki.artifactstore.dataclasses import ArtifactRef

from typing import Any, List, Dict, Union
from pydantic import BaseModel, Field
from datetime import datetime

# ----------------------------
#    RunMetaData
# ----------------------------

class ComponentRunMeta(BaseModel):
    component_id: str

    # Tracking der Eingangsdaten
    input_refs: List[Union[ArtifactRef, str, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Referenzen auf Eingangs-Daten (ArtifactRef, Pfad-Strings oder Metadaten-Dicts)"
    )

    # Hyperparameter & Modell-Configs
    config_summary: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Hyperparameter und Konfiguration dieser Komponente"
    )

    # RunContext der Komponenente
    runcontext_summary: Dict[str, Any] = Field(
        default_factory=dict, 
        description="RunContext mit gemergten Overrides dieser Komponente"
    )
       
    # Output
    outputs_summary: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Attribute-level summary including inline info and ArtifactRefs"
    )

    artifacts: List[ArtifactRef] = Field(
        default_factory=list,
        description="Artifacts produced or consumed by this component run"
    )


class RunMetaData(BaseModel):
    run_id: str

    pipeline_id: str
#    pipeline_version: str

    component_runs: List[ComponentRunMeta] = Field(
        default_factory=list,
        description="All component executions in this run"
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )

    class ConfigDict:
        frozen = True  # RunMetaData should be immutable once created

# ----------------------------
#    PipelineResult
# ----------------------------
class ComponentResultSummary(BaseModel):
    component_id: str

    # Tracking der Eingangsdaten
    input_refs: List[Union[ArtifactRef, str, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Referenzen auf Eingangs-Daten (ArtifactRef, Pfad-Strings oder Metadaten-Dicts)"
    )

    # Hyperparameter & Modell-Configs
    config_summary: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Hyperparameter und Konfiguration dieser Komponente"
    )

    # RunContext der Komponenente
    runcontext_summary: Dict[str, Any] = Field(
        default_factory=dict, 
        description="RunContext mit gemergten Overrides dieser Komponente"
    )
       
    # Output
    outputs_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Fachlich relevante Outputs dieser Komponente"
    )

    artifacts: List[ArtifactRef] = Field(
        default_factory=list,
        description="Referenzen auf Artefakte, die für PipelineResults relevant sind"
    )

# PipelineResult 
class PipelineResults(BaseModel):
    run_id: str
#    pipeline_id: str
#    pipeline_version: str
   
    component_results: List[ComponentResultSummary] = Field(
        default_factory=list,
        description="Fachlich relevante Ergebnisse aller Komponenten"
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class ConfigDict:
        frozen = True  


# Datenklasse für Attribute von Base64 kodierten Bildern (serializer: base64_image)
class Base64Image(BaseModel):
    """Container für Base64-kodierte Bilddaten."""
    content: str  # Der reine Base64-String