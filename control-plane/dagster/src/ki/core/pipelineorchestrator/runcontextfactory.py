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
# ki/core/pipelineorchestrator/runcontextfactory.py

from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, ComponentSpec

import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel

# %%
RunOverrides = Dict[str, Dict[str, Any]]


# %%
class RunContextFactory:
    """
    Baut vollständige RunContexts aus Build-Configs und optionalen Run-Overrides.
    """

    def __init__(self, component_specs: list[ComponentSpec], logger: logging.Logger):
        self._specs = {spec.name: spec for spec in component_specs}
        self._validate_specs()

    # ---------- Helpers for RunOverrides ----------

    @staticmethod
    def _validate_override_keys(
        *,
        component_name: str,
        overrides: Dict[str, Any],
        config_model: type[BaseModel]
    ):
        
        allowed = set(config_model.model_fields.keys())
        unknown = set(overrides.keys()) - allowed
        if unknown:
            raise KeyError(
                f"Unknown override keys for component '{component_name}': {sorted(unknown)}"
            )

    @staticmethod
    def _deep_update(target: Dict[str, Any], updates: Dict[str, Any]) -> None:
        for key, value in updates.items():
            if (
                isinstance(value, dict)
                and isinstance(target.get(key), dict)
            ):
                RunContextFactory._deep_update(target[key], value)
            else:
                target[key] = value
    
    @staticmethod
    def _merge_config(
        *,
        base_config: BaseModel,
        overrides: Dict[str, Any],
        config_class: type[BaseModel],
    ) -> BaseModel:
        data = base_config.model_dump()
        RunContextFactory._deep_update(data, overrides)
        return config_class(**data)
    
    
    # ---------- statische Validierung ----------

    def _validate_specs(self) -> None:
        for name, spec in self._specs.items():
            if spec.run_context_class is None:
                continue

            if not issubclass(spec.run_context_class, BaseRunContext):
                raise TypeError(
                    f"run_context_class of '{name}' must inherit from BaseRunContext"
                )

            if spec.config_class is None:
                raise TypeError(
                    f"Component '{name}' has RunContext but no config_class"
                )

            if not isinstance(spec.build_config, spec.config_class):
                raise TypeError(
                    f"build_config of '{name}' must be instance of "
                    f"{spec.config_class.__name__}"
                )

    # ---------- Public API ----------

    def create_run_contexts(
        self,
        run_overrides: Optional[RunOverrides] = None,
    ) -> Dict[str, Optional[BaseRunContext]]:

        run_overrides = run_overrides or {}
        result: Dict[str, Optional[BaseRunContext]] = {}

        for name, spec in self._specs.items():
            overrides = run_overrides.get(name)

            if spec.run_context_class is None:
                if overrides:
                    raise ValueError(
                        f"Overrides provided for component '{name}' "
                        "which has no RunContext"
                    )
                result[name] = None
                continue

            merged_config = spec.build_config

            if overrides:
                self._validate_override_keys(
                    component_name=name,
                    overrides=overrides,
                    config_model=spec.config_class,
                )
                merged_config = self._merge_config(
                    base_config=merged_config, #spec.build_config,
                    overrides=overrides,
                    config_class=spec.config_class,
                )

            ctx = spec.run_context_class(
                component_name=name,
                config=merged_config,
            )
            result[name] = ctx

        return result

# %%
