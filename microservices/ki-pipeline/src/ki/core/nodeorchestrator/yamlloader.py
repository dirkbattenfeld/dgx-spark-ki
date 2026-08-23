# ki.core.nodeorchestrator.yamlloader.py
# YAML einlesen und parsen

from ki.core.nodeexecutor.dataclasses import NodeConfig

import yaml
import os
from typing import List, Union, Tuple
from pathlib import Path

def load_nodes_from_yaml(yaml_path: Union[str, Path]) -> Tuple[List[NodeConfig], bool]:
    path = Path(yaml_path).resolve() # Macht den Pfad absolut und sauber
    
    if not path.exists():
        raise FileNotFoundError(
            f"\n[YAML-LOADER ERROR] Konfigurationsdatei nicht gefunden!\n"
            f"Versuchter Pfad: {path}\n"
            f"Aktuelles Arbeitsverzeichnis (CWD): {os.getcwd()}"
        )
    
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    # Liste der Nodes holen und in nodes: List[NodeConfig] schreiben
    nodes_raw = data.get("nodes", [])
    nodes: List[NodeConfig] = []

    for node_dict in nodes_raw:
        # Pydantic validiert automatisch die Typen
        node = NodeConfig(**node_dict)
        nodes.append(node)

    # debug_flag aus Abschnitt global holen
    global_config = data.get("global", {})
    debug_mode = global_config.get("debug_mode", False)

    return nodes, debug_mode
