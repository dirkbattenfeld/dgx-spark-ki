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
# ki/core/datapipeline/compexecfactory.py

import logging

from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext, ComponentSpec 


# %%
# -----------------------------
# Component Execution Factory
# -----------------------------

# Instanziiert alle Komponenten der DataPipeline anhand der Specs 

class CompExecFactory:
    def __init__(self, global_build_ctx: GlobalBuildContext, logger: logging.Logger):
        self.logger = logger
        self.global_build_ctx = global_build_ctx
   
    def instantiate_component(self, spec: ComponentSpec):
        """
        ComponentSpec → Instanz
        """
        if spec is None:
            return None
    
        # Sicherheitscheck: Phase 2 muss gelaufen sein
        if spec.config_class and not isinstance(spec.build_config, spec.config_class):
            raise RuntimeError(
                f"Component '{spec.name}' was not enriched before instantiation"
            )
    
        return spec.cls(
            config=spec.build_config,
            global_build_ctx=self.global_build_ctx)
    
    def instantiate_pipeline(self, specs: list[ComponentSpec]) -> list[object]:
        """
        ComponentSpec → Komponenteninstanzen
        - Reihenfolge wie in YAML
        - Mehrere gleiche Typen erlaubt
        """
        components: list[object] = []
    
        for spec in specs:
            components.append(self.instantiate_component(spec))
    
        return components

# %%
