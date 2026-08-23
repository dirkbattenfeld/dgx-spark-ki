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
# ki/pipelines/mlrunner/adapters/.py
from typing import Type

from sklearn.base import BaseEstimator
from ki.pipelines.mlrunner.adapter.registry import adapter_registry
from ki.pipelines.mlrunner.adapter.base import BaseAdapter, ModelCapability
from ki.pipelines.mlrunner.models.base import BaseSpec


# %%
@adapter_registry.register("general_scikit")
class GeneralSciKitAdapter(BaseAdapter):
    """
    Ein Adapter für beliebige sklearn Modelle:
    - nimmt Spec
    - nimmt ModelDef.model_cls (die konkrete sklearn Klasse)
    - baut und trainiert Modell
    """

    capabilities = {ModelCapability.TRAIN, ModelCapability.PREDICT}

    def __init__(self, spec: BaseSpec, model_cls: Type[BaseEstimator]):
        self.spec = spec
        self.model_cls = model_cls
        self.model: BaseEstimator = model_cls(**spec.to_kwargs())

    def build(self, X=None, y=None):
        # sklearn braucht kein Build
        pass

    def train(self, X, y, **kwargs):
        self.model.fit(X, y)

    def predict(self, X):
        return self.model.predict(X)

# %%
