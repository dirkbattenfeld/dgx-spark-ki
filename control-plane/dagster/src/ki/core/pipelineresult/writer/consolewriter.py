# ki/core/pipelineresult/writer.consolewriter.py

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext
from ki.core.pipelineresult.writer.registry import writer_registry

from typing import Any

@writer_registry.register("console")
class ConsoleWriter:
    def __init__(self, logger=None, global_run_ctx: GlobalRunContext = None):
        self.logger = logger

    def write(self, payload: Any) -> None:
        print("\n--- [PERSISTOR OUTPUT] ---")
        if isinstance(payload, str):
            # JSON / Text
            print(payload)
        elif isinstance(payload, bytes):
            # Parquet / Numpy / Pickle
            print(f"<Binary Data: {len(payload)} bytes, Type: {type(payload)}>")
        else:
            # Falls der Serializer direkt ein Objekt (z.B. Dict) durchreicht
            print(f"<Object Data: {payload}>")
        print("--- [END OUTPUT] ---\n")
