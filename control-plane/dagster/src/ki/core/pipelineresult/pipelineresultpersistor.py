# ki.core.pipelineresult.pipelineresultpersistor.py

from ki.core.pipelineresult.pipelineresultpolicy import PolicyOutput, PersistAction
from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, RunMetaData, PipelineResults

class PipelineResultPersistor:
    def __init__(self, global_run_ctx: GlobalRunContext):
        # Initialisierung über den Context (Registry-Zugriff)
        self.ctx = global_run_ctx
        self.logger = self.ctx.run_logger
        self.projectors = global_run_ctx.projector_registry
        self.flatteners = global_run_ctx.flattener_registry
        self.serializers = global_run_ctx.serializer_registry
        self.writers = global_run_ctx.writer_registry

    def persist(self, run_metadata: RunMetaData, policy_output: PolicyOutput) -> PipelineResults:
        """
        Führt die Actions aus und gibt das gewünschte Result-Level zurück.
        """
        # 1. Abarbeitung des Action-Sets (Side-Effects)
        for action in policy_output.action_set:
            self._execute_single_action(run_metadata, action)

        # 2. Rückgabe des gewünschten Projektions-Levels (Data Flow)
        # Wir nutzen den Projektor der Registry, um das Return-Level zu bauen
        projector_cls = self.projectors.get(policy_output.return_level)
        return_projector = projector_cls(logger=self.logger) 
        return return_projector.project(run_metadata=run_metadata)
        
    def _execute_single_action(self, data: RunMetaData, action: PersistAction):
        # 1. Projektion
        projector_cls = self.projectors.get(action.projector_key)
        projector_instance = projector_cls(logger=self.logger) 
        projected = projector_instance.project(run_metadata=data)
                
        # 2. Flattening
        flattener_cls = self.flatteners.get(action.flattener_key)
        flattener_instance = flattener_cls(logger=self.logger)
        flattened = flattener_instance.flatten(projected)
        
        # 3. Serialisierung
        serializer_cls = self.serializers.get(action.serializer_key)
        serializer_instance = serializer_cls() 
        serialized_payload = serializer_instance.serialize(flattened)
        
        # 4. Writing
        writer_cls = self.writers.get(action.writer_key)
        writer_instance = writer_cls(logger=self.logger, global_run_ctx=self.ctx)
        writer_instance.write(serialized_payload, **action.writer_kwargs)