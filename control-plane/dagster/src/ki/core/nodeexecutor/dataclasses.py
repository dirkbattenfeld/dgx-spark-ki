# ki/core/nodeececutor/dataclasses.py
# Datenklasse für NodeConfig

from typing import Union, Dict, List, Optional, Any
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from dataclasses import dataclass

class NodeConfigBase(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    node_id: str
    type: str
    
    # Fan-out Logik mit Templates über expand_node_specs 
    fan_out: Optional[int] = None
    fan_index: Optional[int] = 0 # 0 für kein Fan out
    deps: List[str] = Field(default_factory=list)

    # Pfade
    base_path: Path
    config_path: Path
    build_log_path: Optional[Path] = None
    run_log_path: Optional[Path] = None

    # Konfiguration des Generators
    generator_name: str
    generator_config: Optional[
        Union[Dict[str, Any], List[Dict[str, Any]]]
    ] = None
    
    class ConfigDict:
        # Serialisierung unterstützt Pfade als Strings
        json_encoders = {
            Path: str
        }

class NodeConfig(NodeConfigBase):
    """Klasse für die initiale Konfiguration aus der YAML"""
    pass

class NodeOverrides(NodeConfigBase):
    """Klasse für dynamische Änderungen zur Laufzeit mit Overrides"""
    pass


@dataclass
class UpstreamNodeData:
    """Kapselt das Ergebnis und die Config eines Vorgänger-Nodes."""
    result: Any         # Das Pydantic-Modell des Ergebnisses
    node_config: NodeConfig    # Das NodeConfig Pydantic-Modell


@dataclass
class UpstreamData:
    """Die Upstream Daten für die abhängigen Nodes"""
    nodes: List[UpstreamNodeData]

    def has_data(self) -> bool:
        """Prüft, ob die Liste der Nodes nicht leer ist."""
        return len(self.nodes) > 0

    @property
    def latest(self) -> UpstreamNodeData:
        """Hilfseigenschaft für den Standardfall (1:1 Verbindung)."""
        if not self.nodes:
            # Hier nutzen wir intern has_data() für die Konsistenz
            raise ValueError("Keine Upstream-Daten vorhanden.")
        return self.nodes[-1]
