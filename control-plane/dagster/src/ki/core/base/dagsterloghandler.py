import re
import logging
from typing import Optional, Any

try:
    from dagster import AssetObservation
except ImportError:
    AssetObservation = None

class DagsterLogHandler(logging.Handler):
    def __init__(self, context: Any):
        super().__init__()
        self.context = context
        # Regex sucht nach: dg_obs: schlüssel=wert (auch Floats und wissenschaftliche Notation)
        self.pattern = re.compile(r"dg_obs:\s*([\w\.]+)\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")

    def emit(self, record):
        if not self.context or AssetObservation is None:
            return
        
        msg = record.getMessage()
        match = self.pattern.search(msg)
        
        if match:
            label, value = match.groups()
            try:
                # Senden an Dagster GUI
                self.context.log_event(
                    AssetObservation(
                        asset_key=self.context.asset_key,
                        metadata={label: float(value)}
                    )
                )
            except Exception:
                # Wir wollen nicht, dass ein Logging-Fehler die Pipeline stoppt
                pass
