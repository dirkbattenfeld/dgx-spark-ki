# ki/pipelines/mlrunner/mlrunner.py
from pydantic import BaseModel, ConfigDict
from typing import Optional, ClassVar
from dataclasses import dataclass
import numpy as np

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.mlrunner.models.registry import modeldef_registry
from ki.pipelines.mlrunner.adapter.base import ModelCapability
from ki.pipelines.mlrunner.stratifiedsampler import TrainTestSplit
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext


# %%
class SciKitLearnConfig(BaseModel):
    modeltype: str
    config: dict
    write_artifact: bool = True

@dataclass
class SciKitLearnRunContext(BaseRunContext[SciKitLearnConfig]):
    component_name: str
    config: SciKitLearnConfig
    modeltype_override: Optional[str] = None
    spec_override: Optional[dict] = None
    _pipeline_outputs: ClassVar[list[str]] = ['config']

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )

class SciKitLearnResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    predictions: np.ndarray
    y_test: np.ndarray
    spec: BaseModel

@component_registry.register("ml_runner")
class MLRunner(BaseComponent):

    CONFIG_CLASS = SciKitLearnConfig
    INPUT_CLASS = TrainTestSplit
    OUTPUT_CLASS = SciKitLearnResult
    RUN_CONTEXT_CLASS = SciKitLearnRunContext

    def run(self, data: TrainTestSplit, *, component_ctx, global_ctx):
        model_name = component_ctx.modeltype_override or self.config.modeltype
        model_def: ModelDef = modeldef_registry.get(model_name)
        
        spec_params = component_ctx.config.config
        spec = model_def.spec_cls(**spec_params)
        
        # Adapter über build adapter in model_def
        adapter = model_def.build_adapter(spec)
        
        # --- interne Konvertierung Pandas -> NumPy
        X_train_np = data.X_train.to_numpy()
        X_test_np = data.X_test.to_numpy()
        y_train_np = data.y_train.to_numpy()
        y_test_np = data.y_test.to_numpy()

        if ModelCapability.BUILD in model_def.capabilities:
            adapter.build(X_train_np, y_train_np)
        if ModelCapability.TRAIN in model_def.capabilities:
            adapter.train(X_train_np, y_train_np)
        if ModelCapability.PREDICT in model_def.capabilities:
            preds = adapter.predict(X_test_np)
        else:
            preds = None
                
        result = SciKitLearnResult(
            predictions=preds,
            y_test=y_test_np,
            spec=spec,
        )

        return result

# %%

# %%
