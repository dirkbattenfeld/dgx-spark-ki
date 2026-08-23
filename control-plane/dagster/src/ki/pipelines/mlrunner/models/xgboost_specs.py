from pydantic import BaseModel

from ki.pipelines.mlrunner.models.base import BaseSpec

class XGBoostSpec(BaseSpec, BaseModel):
    n_estimators: int = 100
    max_depth: int = 6
    learning_rate: float = 0.3
    subsample: float = 1.0
    colsample_bytree: float = 1.0
    tree_method: str = "auto" # "gpu_hist" für GPU-Support
