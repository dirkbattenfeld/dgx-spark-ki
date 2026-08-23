# ki/core/pipelineorchestrator/yamlloader.py

import logging
import yaml
from pathlib import Path
from typing import Any, Dict


# %%
class YamlLoader:
    """
    Verantwortlichkeiten:
    - Datei laden (Pfad → Text)
    - YAML parsen (Text → Dict)
    - Vorverarbeitung (optional erweiterbar)
    - Keine Abhängigkeit zu Pipeline, Factory oder Pydantic

    Erweiterbar durch:
    - Env-Variable-Substitution
    - Includes / !include
    - Validierung
    - Logging
    - Templates
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        
    def load(self, path: str | Path) -> Dict[str, Any]:
        """Öffentliche API: Pfad in finalen Config-Dict wandeln."""
        raw_text = self._read_file(path)
        raw_dict = self._parse_yaml(raw_text)
        processed_dict = self._postprocess(raw_dict)
        return processed_dict

    # ---------------------------------------------------------
    # interne Schritte – modularisiert, unabhängig voneinander
    # ---------------------------------------------------------

    def _read_file(self, path: str | Path) -> str:
        """Liest Dateiinhalt, ohne Parsing-Logik."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        return p.read_text(encoding="utf-8")

    def _parse_yaml(self, text: str) -> Dict[str, Any]:
        """Parst YAML-Text in ein Dict."""
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"YAML parsing error: {e}")

    def _postprocess(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hook für spätere Erweiterungen.
        Standard: keine Veränderung.
        Beispiele für Erweiterungen:
        - ${ENV}-Substitution
        - Includes
        - Defaults
        """
        return cfg

