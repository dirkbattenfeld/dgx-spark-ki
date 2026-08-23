# ki/core/datapipeline/datapipeline.py

from ki.core.nodeexecutor.dataclasses import UpstreamData
from ki.core.datapipeline.datapipeline_dataclasses import ComponentSpec, GlobalBuildContext, BaseRunContext, GlobalRunContext, ComponentRunMeta, RunMetaData, PipelineResults
from ki.core.datapipeline.compexecfactory import CompExecFactory
from ki.core.datapipeline.artifactpolicy import ArtifactPersistencePolicy
from ki.core.datapipeline.runmetaprojector import ComponentRunMetaProjector
from ki.core.pipelineresult.pipelineresultpolicy import PipelineResultPolicy
from ki.core.pipelineresult.pipelineresultpersistor import PipelineResultPersistor

import logging
from typing import Optional, Dict, List, Any
import os
from datetime import datetime

token = os.getenv("HF_TOKEN", None)

class Pipeline:
    def __init__(self, pipeline_specs: list[ComponentSpec], 
                 global_build_ctx: GlobalBuildContext,
                 upstream_data: UpstreamData): 
        self.pipeline_specs = pipeline_specs
        self.global_build_ctx = global_build_ctx
        self.upstream_data = upstream_data

        # Policies & Projektoren
        self._artifact_policy = None
        self._run_meta_projector = None
        self._result_policy = None
        self._result_persistor = None
       
    def _validate_run_specs(self, logger: logging.Logger):
        """
        Statische Validierung der Pipeline vor Ausführung
        """
        logger.debug("Validating pipeline run specifications.")
        available_outputs: set[type] = set()
        available_outputs.add(UpstreamData)
        for i, spec in enumerate(self.pipeline_specs):
           # INPUT_CLASS prüfen
            if spec.input_class is not None:
                if spec.input_class not in available_outputs:
                    logger.error(
                        f"Pipeline invalid at position {i} ({spec.name}): "
                        f"Required input {spec.input_class.__name__} not available. "
                        f"Available: {[c.__name__ for c in available_outputs]}"
                    )
                    raise RuntimeError(
                        f"Pipeline invalid at position {i} ({spec.name}): "
                        f"Required input {spec.input_class.__name__} not available. "
                        f"Available: {[c.__name__ for c in available_outputs]}"
                    )

            # OUTPUT_CLASS prüfen
            if spec.output_class is None:
                logger.error(f"Component '{spec.name}' has no OUTPUT_CLASS defined")
                raise RuntimeError(
                    f"Component '{spec.name}' has no OUTPUT_CLASS defined"
                )

            available_outputs.add(spec.output_class)
        logger.debug("Pipeline run specifications validated successfully.")

        
    def run(self,*, 
            comp_run_contexts: Dict[str, Optional[BaseRunContext]],
            global_ctx: GlobalRunContext) -> PipelineResults:

        logger = global_ctx.run_logger
        """
        Führt die Pipeline sequentiell aus.
        """
        logger.info("Starting pipeline execution.")
        
        # ToDo: Pre-Run-Validierung
        self._validate_run_specs(logger=logger)

        # CompExecFactory erzeugen und Komponenten bauen
        logger.debug("Initializing CompExecFactory for pipeline components.")
        exec_factory = CompExecFactory(self.global_build_ctx, logger)
        
        # Komponenten instanziieren
        logger.info("Instantiating pipeline components.")
        self.components = exec_factory.instantiate_pipeline(self.pipeline_specs)
        logger.info(f"{len(self.components)} components instantiated.")
        
        # Wiring zur Laufzeit
        self._artifact_policy = ArtifactPersistencePolicy(
            global_ctx=global_ctx,        
            logger=logger,
            max_inline_dict_size=10,
            allow_inferred_serializer=True
        )
        self._run_meta_projector = ComponentRunMetaProjector(logger=logger)
        self._result_policy = PipelineResultPolicy(global_run_ctx=global_ctx)
        self._result_persistor = PipelineResultPersistor(global_run_ctx=global_ctx)

        # Datapool initialisieren
        datapool: dict[type, object] = {}
        # Upstream Daten in den Datepool legen
        datapool[UpstreamData] = self.upstream_data
        logger.debug("Datapool initialized.")

        # Metadatensammlung für Komponenten initialisieren
        component_run_metas: List[ComponentRunMeta] = []
        
        # Komponenten iterieren
        for spec, component in zip(self.pipeline_specs, self.components):
            logger.info(f"Running component '{spec.name}'.")
            
            # ---- Input bestimmen ----
            if spec.input_class is None:
                input_data = None
                logger.debug(f"Component '{spec.name}' has no input.")
            else:
                input_data = datapool[spec.input_class]
                logger.debug(
                    f"Component '{spec.name}' input fetched from datapool: {spec.input_class.__name__}"
                )
                
            # ---- RunContext der Komponente holen
            component_ctx = comp_run_contexts.get(spec.name)
            if component_ctx is None:
                logger.warning(f"No RunContext provided for component '{spec.name}'.")
                
            # ---- Komponente ausführen ----
            output = component.run(
                input_data,
                component_ctx=component_ctx,
                global_ctx=global_ctx,
            )
            logger.debug(f"Component '{spec.name}' execution finished.")
            
            # ---- Output validieren ----
            if not isinstance(output, spec.output_class):
                logger.error(
                    f"Component '{spec.name}' returned {type(output).__name__}, "
                    f"expected {spec.output_class.__name__}"
                )
                raise RuntimeError(
                    f"Component '{spec.name}' returned "
                    f"{type(output).__name__}, expected {spec.output_class.__name__}"
                )

            # ---- Output im Datapool ablegen ----
            datapool[spec.output_class] = output
            logger.debug(f"Output of component '{spec.name}' stored in datapool.")
                
            # Artifact-Persistenz
            # Die Policy entscheidet anhand des Typs von 'output', was gespeichert wird
            artifact_refs = self._artifact_policy.persist(
                value=output,
                component_name=spec.name,
                global_ctx=global_ctx,
            )

            # ---- Run Metadaten Projektion für Komponente aus Output generieren
            component_run_meta = self._run_meta_projector.project(
                component_spec=spec,
                output=output, 
                global_ctx=global_ctx,
                run_ctx=component_ctx,
                artifact_refs=artifact_refs,
            )
            
            component_run_metas.append(component_run_meta)
            
        # ----- RunMetaData erzeugen ----
        run_metadata = RunMetaData(
            run_id = f"Path={global_ctx.run_path} with ID: {global_ctx.run_id}",
            pipeline_id = "ToDo: Pipeline ID",
            component_runs = component_run_metas,
            created_at = datetime.utcnow()
        )

        # ---- PipelineResults erzeugen und persistieren ---- 
        policy_output = self._result_policy.resolve(run_metadata)

        pipeline_results = self._result_persistor.persist(
            run_metadata=run_metadata, 
            policy_output=policy_output
        )

        # ---- Ergebnis zurückgeben ----
        logger.info(f"Data Pipeline execution finished. Return Level: {policy_output.return_level}")
        return pipeline_results
