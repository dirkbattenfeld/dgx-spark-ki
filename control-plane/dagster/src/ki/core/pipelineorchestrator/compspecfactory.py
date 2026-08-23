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
# ki/core/pipelineorchestrator/compspecfactory.py
from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext, ComponentSpec

import logging
from typing import Dict, List, Optional


# %%
# -----------------------------
# ComponentSpecFactory
# -----------------------------
class CompSpecFactory:
    def __init__(self, global_build_ctx: GlobalBuildContext): 
        self.global_build_ctx = global_build_ctx
        self.logger = self.global_build_ctx.build_logger

    # -------- Phase 1: Build ComponentSpecs --------
    def build_component_spec(self, node: dict | None) -> Optional[ComponentSpec]:
        if not node:
            return None
    
        comp_name = node.get("name")
    
        # Registry nur zur Existenzprüfung
        comp_cls = self.global_build_ctx.component_registry.get(comp_name)
        if not comp_cls:
            if self.logger:
                self.logger.warning(
                    "Registry %s: Component '%s' not found!",
                    type(self.global_build_ctx.component_registry).__name__,
                    comp_name,
                )
            return None
    
        # Config Dict der Komponente holen
        config_dict = node.get("config", {})
    
        return ComponentSpec(
            name=comp_name,
            cls=comp_cls,                 # Klassenreferenz OK
            build_config=config_dict,    # immer dict in Phase 1
        )

    def build_component_spec_list(self, nodes: List[dict]) -> List[ComponentSpec]:
        specs = []
        for node in nodes:
            spec = self.build_component_spec(node)
            if spec is not None:
                specs.append(spec)
        return specs

    def build_pipeline_specs(self, pipeline_cfg: dict) -> list[ComponentSpec]:
        """
        Phase 1 – Build ComponentSpecs (roh)
        - Dynamisch aus pipeline["components"]
        - Beliebige Anzahl von Komponenten gleichen Typs möglich
        - Keine festen Keys
        """
        specs: list[ComponentSpec] = []
    
        for node in pipeline_cfg.get("components", []):
            spec = self.build_component_spec(node)
            if spec:
                specs.append(spec)
    
        return specs

    
    # -------- Phase 2: Enrich ComponentSpecs from Registry and nodes: Config.dict --------   
    
    def enrich_component_spec(
        self,
        spec: ComponentSpec | None
        ) -> ComponentSpec | None:
        if spec is None:
            return None

        comp_cls = spec.cls

        # 1) Metadaten aus der Komponente ziehen
        config_class = getattr(comp_cls, "CONFIG_CLASS", None)
        input_class = getattr(comp_cls, "INPUT_CLASS", None)
        output_class = getattr(comp_cls, "OUTPUT_CLASS", None)
        run_context_class = getattr(comp_cls, "RUN_CONTEXT_CLASS", None)

        # 2) Das build_config Dict aus der build_specs Stage aus den specs holen und 
        merged_config_dict = {}
        if isinstance(spec.build_config, dict):
            merged_config_dict.update(spec.build_config)
        
        # 3) in das neu erstellte Pydantic Config-Objekt injizieren
        config_obj = None
        if config_class:
            try:
                # Pydantic-Klasse oder normale Config-Klasse instanziieren
                config_obj = config_class(**merged_config_dict)
            except Exception as e:
                raise ValueError(
                    f"Invalid config for component '{spec.name}': {e}"
                ) from e
           
        return ComponentSpec(
            name=spec.name,
            cls=comp_cls,
            config_class=config_class,
            input_class=input_class,
            output_class=output_class,
            run_context_class=run_context_class,
            build_config=config_obj
        )

    def enrich_component_spec_list(
        self,
        specs: list[ComponentSpec]
        ) -> list[ComponentSpec]:
        return [
            self.enrich_component_spec(spec)
            for spec in specs
            if spec is not None
        ]

    def enrich_pipeline_specs(
        self,
        specs: list[ComponentSpec]
        ) -> list[ComponentSpec]:
        """
        Phase 2 – Specs anreichern
        - Fügt CONFIG_CLASS, INPUT_CLASS, OUTPUT_CLASS und defaults hinzu
        """
        return [
            self.enrich_component_spec(spec)
            for spec in specs
        ]

# %%
