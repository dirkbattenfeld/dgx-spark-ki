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
from dataclasses import dataclass
from sklearn.base import BaseEstimator
from typing import Optional, Type, Set

from ki.pipelines.mlrunner.adapter.base import BaseAdapter
from ki.pipelines.mlrunner.adapter.registry import adapter_registry


#    """Alle Specs müssen mindestens to_kwargs implementieren"""
#    def to_kwargs(self) -> dict:
#        return self.dict() if hasattr(self, "dict") else {}

class BaseSpec:
    def to_kwargs(self) -> dict:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        if hasattr(self, "dict"):
            return self.dict()
        return {}


@dataclass(frozen=True)
class ModelDef:
    name: str
    spec_cls: Type[BaseSpec]
    model_cls: Type[BaseEstimator]
    adapter_key: str                   
    capabilities: Set[str]

    def build_adapter(self, spec: BaseSpec) -> BaseAdapter:
        """
        Zentrale, einzige Stelle zur Adapter-Erzeugung.
        """
        adapter_cls = adapter_registry.get(self.adapter_key)
        return adapter_cls(
            spec=spec,
            model_cls=self.model_cls,
        )
