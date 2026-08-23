# ki/core/base/logging.py
from ki.core.base.dagsterloghandler import DagsterLogHandler

import logging
from pathlib import Path
from typing import Optional, Any

def _next_log_file(log_dir: Path, prefix: str) -> Path:
    """
    Findet den nächsten freien logXXXX.log-Dateinamen im Verzeichnis.
    Z.B. run0001.log, run0002.log ...
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(f for f in log_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".log")
    if not existing:
        next_index = 0
    else:
        # letzte Datei extrahieren und Index erhöhen
        last_index = max(int(f.stem[len(prefix):]) for f in existing)
        next_index = last_index + 1
    return log_dir / f"{prefix}{next_index:04d}.log"


def configure_logger(
    name: str,
    log_dir: Optional[Path] = None,
    file_level: Optional[int] = logging.INFO,
    console_level: Optional[int] = logging.INFO,
    log_format: str = "[%(asctime)s] %(name)s %(levelname)s %(run_id_optional)s: %(message)s",
    file_prefix: str = "log",
    dagster_context: Optional[Any] = None  # DagsterContext für Asset Observation Handling
) -> logging.Logger:
    """
    Konfiguriert einen separaten Logger mit optional FileHandler und ConsoleHandler.
    Build- und Run-Logger können unabhängig konfiguriert werden.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # wichtig, sonst landen Logs zusätzlich im Root-Logger

    # ---- generischer Formatter ----
    context_fields = ["run_id"]
    class GenericContextFormatter(logging.Formatter):
        def format(self, record):
            for key in context_fields:
                if hasattr(record, key) and getattr(record, key):
                    setattr(record, f"{key}_optional", f" [{key}={getattr(record, key)}]")
                else:
                    setattr(record, f"{key}_optional", "")
            return super().format(record)

    formatter = GenericContextFormatter(log_format)

    # ---- Console Handler ----
    if console_level is not None:
        console_handler_exists = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
        if not console_handler_exists:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(console_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    # ---- File Handler ----
    if log_dir is not None and file_level is not None:
        file_path = _next_log_file(log_dir, file_prefix)
        file_handler_exists = any(isinstance(h, logging.FileHandler) and h.baseFilename == str(file_path) 
                                  for h in logger.handlers)
        if not file_handler_exists:
            file_handler = logging.FileHandler(file_path, mode="a")
            file_handler.setLevel(file_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    # ---- Dagster Log Handler ----
    if dagster_context is not None:
        # Verhindern, dass doppelte Dagster-Handler hinzugefügt werden
        if not any(isinstance(h, DagsterLogHandler) for h in logger.handlers):
            dg_handler = DagsterLogHandler(dagster_context)
            # Der Handler sollte auf INFO laufen, damit er dg_obs mitbekommt
            dg_handler.setLevel(logging.INFO) 
            logger.addHandler(dg_handler)

    return logger


# Fügt einem Logger einen LoggerAdapter mit beliebigen Kontextinformationen hinzu
# Nur der zuletzt hinzugefügte Kontext ist aktiv

class ContextLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, **context):
        super().__init__(logger, context)
