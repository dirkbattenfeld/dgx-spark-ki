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
# ki/pipelines/mlrunner/adapter/base.py
from typing import Set
from abc import ABC, abstractmethod


# %%
class ModelCapability:
    BUILD = "build"
    TRAIN = "train"
    PREDICT = "predict"
    LOAD = "load"
    SAVE = "save"

class BaseAdapter(ABC):
    capabilities: Set[str]

    @abstractmethod
    def build(self, X=None, y=None):
        pass

    @abstractmethod
    def train(self, X, y, **kwargs):
        pass

    @abstractmethod
    def predict(self, X):
        pass

# %%
