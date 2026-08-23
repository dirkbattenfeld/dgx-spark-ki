# ki/core/pipelineresult/writer/filewriter.py

from ki.core.pipelineresult.writer.registry import writer_registry
from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext

from typing import Optional, Any
import logging
 
@writer_registry.register("file")
class FileWriter:
    def __init__(self, logger: Optional[logging.Logger] = None, global_run_ctx: GlobalRunContext = None):
        self.logger = logger or logging.getLogger(__name__)
        self.ctx = global_run_ctx

    def write(self, payload: Any, filename: Optional[str] = None, **kwargs) -> None:
        # Fallback: Wenn kein Name da ist, generiere einen Standardnamen
        if not filename:
            filename = "run_summary.json"

        dest_path = self.ctx.run_path / filename

        mode = "w" if isinstance(payload, str) else "wb"
        encoding = "utf-8" if isinstance(payload, str) else None

        with open(dest_path, mode, encoding=encoding) as f:
            f.write(payload)

        self.logger.info(f"Run Summary gespeichert: {dest_path}")
