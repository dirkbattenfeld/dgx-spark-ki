# ki/core/pipelineorchestrator/pipelineorchestrator.py

# NodeExecutor ruft initialize_pipeline im PipelineOrchestrator auf der PipelineInitializer nutzt
# ToDo: Kann das vereinfacht werden?

from ki.core.nodeexecutor.dataclasses import UpstreamData
from ki.core.pipelineorchestrator.globalbuildcontextfactory import GlobalBuildContextFactory
from ki.core.pipelineorchestrator.globalruncontextfactory import GlobalRunContextFactory
from ki.core.pipelineorchestrator.runcontextfactory import RunContextFactory
from ki.core.pipelineorchestrator.compspecfactory import CompSpecFactory
from ki.core.pipelineorchestrator.yamlloader import YamlLoader
from ki.core.pipelineorchestrator.generator.registry import generator_registry
from ki.core.datapipeline.datapipeline import Pipeline
from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext

import logging
from pathlib import Path
from typing import Any

class PipelineInitializer:
    def __init__(self, global_build_ctx: GlobalBuildContext, upstream_data: UpstreamData):
        self.global_build_ctx = global_build_ctx
        self.upstream_data = upstream_data

    def initialize_pipeline(self, pipeline_specs: list) -> Pipeline:
        # Component-Objekte in Pipeline initialisieren
        return Pipeline(pipeline_specs, self.global_build_ctx, self.upstream_data)

class PipelineOrchestrator:
    def __init__(self,
                 node_id: str,
                 config_path: Path, 
                 base_path: Path,
                 build_logger: logging.Logger,
                 run_logger: logging.Logger,
                 generator_name: str,
                 generator_config: Any,
                 upstream_data: Any):
        self.node_id = node_id
        self.config_path = config_path
        self.base_path=base_path
        self.build_logger = build_logger
        self.run_logger = run_logger
        self.generator_name=generator_name
        self.generator_config=generator_config
        self.yaml_config = None
        self.global_config = None
        self.global_build_ctx = None
        self.pipeline_specs = None
        self.pipeline = None
        self.upstream_data = upstream_data

    # -------- BUILDTIME --------
    def build(self):
        # YAML laden
        loader = YamlLoader(logger=self.build_logger)
        self.yaml_config = loader.load(self.config_path)
        pipeline_config = self.yaml_config.get("pipeline", self.yaml_config)
        self.global_config = self.yaml_config.get("global", self.yaml_config)
    
        # GlobalBuildContext erstellen
        self.global_build_ctx = GlobalBuildContextFactory(base_path=self.base_path, logger=self.build_logger).create()
        
        # ComponentSpecs bauen
        spec_factory = CompSpecFactory(self.global_build_ctx) 
        raw_specs = spec_factory.build_pipeline_specs(pipeline_config)
        self.pipeline_specs = spec_factory.enrich_pipeline_specs(raw_specs)

    # -------- PIPELINE INITIALISIEREN --------
    def initialize_pipeline(self):
        initializer = PipelineInitializer(self.global_build_ctx, self.upstream_data)
        self.pipeline = initializer.initialize_pipeline(self.pipeline_specs)


    # -------- RUNTIME --------
    def run(self):
        if not self.pipeline:
            raise RuntimeError("Pipeline muss zuerst initialisiert werden!")
    
        # --- Factories ---
        global_run_context_factory = GlobalRunContextFactory(
            global_build_ctx=self.global_build_ctx,
            node_id=self.node_id, 
            yaml_global=self.global_config,
            logger=self.run_logger
        )
        run_context_factory = RunContextFactory(self.pipeline_specs, logger=self.run_logger)
    
        # --- Generator erzeugen ---
        gen_cls = generator_registry.get(self.generator_name)
        generator_instance = gen_cls.from_config(
            self.generator_config,
            logger=self.run_logger
        )
        expects_feedback = generator_instance.ExpectsFeedback
        generator_iter = generator_instance.generate()
    
        results = []
        self.run_logger.info(f"Starte Pipeline-Ausführung mit Generator: {self.generator_name}")   
        
        # --- erster Vorschlag ---
        try:
            overrides = next(generator_iter)
        except StopIteration:
            return results  # Generator liefert nichts
        
        iteration_count = 0
        while True:
            iteration_count += 1
            self.run_logger.info(f"--- Beginne Iteration {iteration_count} ---")
            
            # --- Pipeline ausführen ---
            global_run_ctx = global_run_context_factory.create(self.run_logger)
            component_run_contexts = run_context_factory.create_run_contexts(overrides)
            self.run_logger.info(f"Anwendung der Overrides für Iteration {iteration_count}: {overrides}")
            result = self.pipeline.run(
                comp_run_contexts=component_run_contexts,
                global_ctx=global_run_ctx)
            self.run_logger.info(f"Iteration {iteration_count} erfolgreich abgeschlossen.")
            results.append(result)
    
            try:
                if expects_feedback:
                    # Der Generator extrahiert sich, was er braucht
                    feedback_data = generator_instance.process_feedback(result)
                    # Und bekommt es via send() zurück
                    self.run_logger.info(f"Feedback an Generator gesendet.")
                    overrides = generator_iter.send(feedback_data)
                else:
                    # Generator ohne feedback
                    overrides = next(generator_iter)
            
            except StopIteration:
                self.run_logger.info(f"Generator signalisiert Ende der Ausführung (StopIteration nach {iteration_count} Durchläufen).")
                break
            except Exception as e:
                self.run_logger.error(f"Schwerwerwiegender Fehler im Generator-Loop bei Iteration {iteration_count}: {str(e)}")
                raise e

        self.run_logger.info("Pipeline-Run beendet.")
        return results
       