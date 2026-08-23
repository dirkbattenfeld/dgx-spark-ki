# ki/pipelines/mlrunner/csv_loader.py
from pathlib import Path
import pandas as pd
from pydantic import BaseModel, ConfigDict
from dataclasses import dataclass
from typing import Optional

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext


class CSVLoaderConfig(BaseModel):
    path: Path


@dataclass
class CSVLoaderRunContext(BaseRunContext[CSVLoaderConfig]):
    component_name: str
    config: CSVLoaderConfig
    path_override: Optional[Path] = None

    def __post_init__(self):
        # --- keine Änderung, super() bleibt ---
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )

class RawCSVData(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    df: pd.DataFrame


@component_registry.register("csvloader")
class CSVLoader(BaseComponent):

    CONFIG_CLASS = CSVLoaderConfig
    INPUT_CLASS = None
    OUTPUT_CLASS = RawCSVData
    RUN_CONTEXT_CLASS = CSVLoaderRunContext

    def run(self, data, *, component_ctx, global_ctx):
        path = component_ctx.path_override or self.config.path
        df = pd.read_csv(path)
        return RawCSVData(df=df)


