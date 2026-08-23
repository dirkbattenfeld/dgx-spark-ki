# /libs/pipeline/obersavability.py

import functools
import json
import logging
import os
import sys
import time
import traceback
from enum import Enum
from typing import Callable, Optional
from pydantic import BaseModel, Field

from collections.abc import Mapping, Sequence


def flatten(obj, prefix="", max_depth=3, depth=0):
    """
    function for flattening a dict recursive
    """
    
    result = {}

    if depth > max_depth:
        result[prefix] = str(obj)
        return result

    # dict-like
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            new_key = f"{prefix}_{k}" if prefix else k
            result.update(flatten(v, new_key, max_depth, depth + 1))

    # list-like (ABER NICHT string)
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
        # NICHT explodieren → aggregieren
        result[prefix + "_len"] = len(obj)

        # optional: nur erste Elemente
        for i, item in enumerate(obj[:3]):  # cap!
            new_key = f"{prefix}_{i}"
            result.update(flatten(item, new_key, max_depth, depth + 1))

    else:
        result[prefix] = obj

    return result


# --- 1. CONFIGURATION INTERFACE ---
class SimpleTraceConfig(BaseModel):
    filepath: str = Field(default="logs/pipeline_execution.log")
    log_full_input: bool = Field(default=True, description="Wenn False, werden nur Feldnamen geloggt")
    
    # Die 4 unabhängigen Zielkonfigurationen (Standard: alles im Terminal)
    trace_to_terminal: bool = Field(default=False)
    trace_to_file: bool = Field(default=True)
    data_to_terminal: bool = Field(default=False)
    data_to_file: bool = Field(default=True)
    
_ACTIVE_CONFIG: Optional[SimpleTraceConfig] = None

def configure_observability(config: SimpleTraceConfig):
    """Wird einmalig beim App-Start aufgerufen."""
    global _ACTIVE_CONFIG
    _ACTIVE_CONFIG = config
    _setup_logger(config)

# --- 2. LOGGER INITIALISIERUNG ---
class CompactJsonFormatter(logging.Formatter):
    """Formatiert das Log-Payload als kompakten JSON-Einzeiler (JSON Lines) für Dateien."""
    def format(self, record):
        # Wenn wir ein Dict übergeben, serialisieren wir es als kompakte Zeile
        if isinstance(record.msg, dict):
            return json.dumps(record.msg, ensure_ascii=False)
        return super().format(record)

class PrettyJsonFormatter(logging.Formatter):
    """Formatiert das Log-Payload mit Einrückungen für das Terminal."""
    def format(self, record):
        if isinstance(record.msg, dict):
            if record.msg.get("status") == "failed":
                prefix = "🚨 Step-Error:\n"
            elif "Trace" in record.name:
                prefix = "⏱️ Step-Trace (Table):\n"
            else:
                prefix = "🌳 Step-Data (Tree):\n"
                
            formatted = json.dumps(record.msg, indent=2, ensure_ascii=False)
            return f"{prefix}{formatted}"
        return super().format(record)
    
        
def _setup_logger(config: SimpleTraceConfig):
    """Erstellt dynamisch getrennte Logger für Trace und Data basierend auf den Flags."""
    
    logger_trace = logging.getLogger("StreamPipe.Trace")
    logger_data = logging.getLogger("StreamPipe.Data")
    
    # Verhindert die Weiterleitung dieser Logger an den Root-Logger mit Terminalausgabe
    logger_trace.propagate = False
    logger_data.propagate = False
    
    logger_trace.setLevel(logging.INFO)
    logger_data.setLevel(logging.INFO)
    
    # Verhindert doppelte Handler bei mehrmaligem Aufruf
    if logger_trace.handlers or logger_data.handlers:
        return

    # Generierung der Pfade durch Splitten vor der Dateiendung
    base_path, ext = os.path.splitext(config.filepath)
    trace_filepath = f"{base_path}_trace{ext}"
    data_filepath = f"{base_path}_data{ext}"

    # --- FILE TARGETS ---
    if config.trace_to_file or config.data_to_file:
        os.makedirs(os.path.dirname(config.filepath), exist_ok=True)

    if config.trace_to_file:
        file_handler_trace = logging.FileHandler(trace_filepath, encoding="utf-8")
        file_handler_trace.setFormatter(CompactJsonFormatter())
        logger_trace.addHandler(file_handler_trace)
        
    if config.data_to_file:
        file_handler_data = logging.FileHandler(data_filepath, encoding="utf-8")
        file_handler_data.setFormatter(CompactJsonFormatter())
        logger_data.addHandler(file_handler_data)

    # --- TERMINAL TARGETS ---
    if config.trace_to_terminal:
        stream_handler_trace = logging.StreamHandler(sys.stdout)
        stream_handler_trace.setFormatter(PrettyJsonFormatter())
        logger_trace.addHandler(stream_handler_trace)
        
    if config.data_to_terminal:
        stream_handler_data = logging.StreamHandler(sys.stdout)
        stream_handler_data.setFormatter(PrettyJsonFormatter())
        logger_data.addHandler(stream_handler_data)


# --- 3. THE GENERIC DECORATOR ---
def trace_action(step_name: str):
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            config = _ACTIVE_CONFIG or SimpleTraceConfig()
            logger_trace = logging.getLogger("StreamPipe.Trace")
            logger_data = logging.getLogger("StreamPipe.Data")
                        
            input_data = args[0] if args else kwargs.get("input_data")
            
            # 1. Extraktion des Input-Snapshots als echtes Dictionary
            input_snapshot = {}
            if input_data and hasattr(input_data, "model_dump"):
                if config.log_full_input:
                    input_snapshot = input_data.model_dump()
                else:
                    input_snapshot = {"fields_present": list(input_data.model_fields.keys())}
            else:
                input_snapshot = {"raw": str(input_data)}

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                status = getattr(result, "status", "success")
                
                output_snapshot = {}
                metrics_snapshot = {}
                
                # metriks_snapshot und output_snapshot trennen
                if result is not None:
                    if hasattr(result, "model_dump"):
                        output_snapshot = flatten(result.model_dump())
                    elif isinstance(result, dict):
                        output_snapshot = flatten(result.copy())
                    else:
                        output_snapshot = {"value": str(result)}
                
                if isinstance(output_snapshot, dict) and "extras" in output_snapshot:
                    metrics_snapshot = output_snapshot.pop("extras")    
                
                # 2. Das strukturierte Log-Payload bauen
                log_payload_trace = {
                    "step": step_name,
                    "status": status,
                    "duration_s": round(duration, 3)
                    } 
                
                log_payload_data = {
                    "step": step_name,
                    "status": status,
                    "output": output_snapshot,
                    "metrics": metrics_snapshot
                    }
                
                # 3. Loggen des TraceLogs und des DataLogs
                logger_trace.info(log_payload_trace)
                logger_data.info(log_payload_data)
                return result

            except Exception as e:
                duration = time.time() - start_time
                
                error_payload_trace = {
                    "step": step_name,
                    "status": "failed",
                    "duration_s": round(duration, 3), 
                }
                
                error_payload_data = {
                    "step": step_name,
                    "status": "failed",
                    "duration_s": round(duration, 3),
                    "error": type(e).__name__,
                    "message": str(e),
                    "input": input_snapshot,
                    "traceback": traceback.format_exc().splitlines() 
                }
                
                logger_trace.error(error_payload_trace)               
                logger_data.error(error_payload_data)
                
                raise e
        return wrapper
    return decorator
