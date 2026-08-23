# ki/pipelines/mlrunner/stratifiedsampler.py
from pydantic import BaseModel, ConfigDict
from dataclasses import dataclass
from sklearn.model_selection import train_test_split
from typing import Optional
import pandas as pd

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.mlrunner.csvloader import RawCSVData
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext


class StratifiedSamplerConfig(BaseModel):
    target_column: str  # Name der Zielspalte
    test_size: float = 0.2
    random_state: Optional[int] = None

@dataclass
class StratifiedSamplerRunContext(BaseRunContext[StratifiedSamplerConfig]):
    component_name: str
    config: StratifiedSamplerConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )

class TrainTestSplit(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series
    

@component_registry.register("stratifiedsampler")
class StratifiedSampler(BaseComponent):

    CONFIG_CLASS = StratifiedSamplerConfig
    INPUT_CLASS = RawCSVData
    OUTPUT_CLASS = TrainTestSplit
    RUN_CONTEXT_CLASS = StratifiedSamplerRunContext

    def run(self, data: RawCSVData, *, component_ctx, global_ctx):
        df = data.df
        y = df[self.config.target_column]
        X = df.drop(columns=[self.config.target_column])

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=self.config.test_size,
            random_state=self.config.random_state,
            stratify=y,
        )

        return TrainTestSplit(
            X_train=X_train,
            X_test=X_test,
            y_train=y_train,
            y_test=y_test,
        )

# %%
