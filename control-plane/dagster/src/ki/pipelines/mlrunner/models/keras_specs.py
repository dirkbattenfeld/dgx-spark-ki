# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.18.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
# ki/pipelines/mlrunner/models/keras_specs.py
from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional

from ki.pipelines.mlrunner.models.base import BaseSpec


# %%
@dataclass
class DenseLayerSpec(BaseModel):
    units: int
    activation: str = "relu"

class KerasDenseSpec(BaseSpec, BaseModel):
    layers: List[DenseLayerSpec]
    optimizer: str = "adam"
    loss: str = "categorical_crossentropy"
    metrics: List[str] = ["accuracy"]
    epochs: int = 20
    learning_rate: float = 0.001
    batch_size: int = 32
    task_type: str = "classification"  # "classification" oder "regression"
    input_dim: int
    num_classes: Optional[int] = None

# %%
