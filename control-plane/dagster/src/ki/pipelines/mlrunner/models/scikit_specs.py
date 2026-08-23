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
# ki/pipelines/mlrunner/models/scikit_specs.py
# SCIKIT Learn Specs
from pydantic import BaseModel
from typing import Optional

from ki.pipelines.mlrunner.models.base import BaseSpec
from ki.pipelines.mlrunner.models.registry import spec_registry


# %%
@spec_registry.register("randomforest")
class RandomForestSpec(BaseSpec, BaseModel):
    n_estimators: int = 100
    max_depth: Optional[int] = None
    min_samples_split: int = 2

@spec_registry.register("gradient_boosting")
class GradientBoostingSpec(BaseSpec, BaseModel):
    n_estimators: int = 100
    learning_rate: float = 0.1
    max_depth: Optional[int] = 3

@spec_registry.register("logistic_regression")
class LogisticRegressionSpec(BaseSpec, BaseModel):
    penalty: str = "l2"
    C: float = 1.0
    solver: str = "lbfgs"
    max_iter: int = 100

@spec_registry.register("svc")
class SVCSpec(BaseSpec, BaseModel):
    C: float = 1.0
    kernel: str = "rbf"
    degree: int = 3

# %%
