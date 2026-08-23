# ki/core/datapipeline/resultprojector.py

from ki.core.datapipeline.datapipeline_dataclasses import PipelineResults, RunMetaData, ComponentResultSummary
from ki.core.pipelineresult.projector.registry import projector_registry
import logging
from typing import Optional, Dict, Any


@projector_registry.register("results")
class PipelineResultProjector:
    """
    Projiziert RunMetaData auf PipelineResults und filtert dabei
    outputs, config und runcontext basierend auf dem 'pipeline_output' Flag.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def _filter_summary(self, summary_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hilfsmethode, um ein Summary-Dict (mit attr_info Strukturen) zu filtern.
        Behält nur Werte, die 'pipeline_output': True haben und nicht 'drop': True sind.
        """
        filtered = {}
        for attr_name, attr_info in summary_dict.items():
            # Falls attr_info kein Dict ist (Safety Check), überspringen oder direkt übernehmen
            if not isinstance(attr_info, dict):
                continue
                
            if attr_info.get("drop"):
                continue
            
            if attr_info.get("pipeline_output"):
                filtered[attr_name] = attr_info.get("value")
        
        return filtered


    def project(self, run_metadata: RunMetaData) -> PipelineResults:
        self.logger.debug(f"Projecting filtered results for run {run_metadata.run_id}")

        component_results = []

        for crm in run_metadata.component_runs:
            filtered_outputs = self._filter_summary(crm.outputs_summary)
            filtered_config = self._filter_summary(crm.config_summary)
            filtered_runcontext = self._filter_summary(crm.runcontext_summary)

            if not any([filtered_outputs, filtered_config, filtered_runcontext]):
                continue 

            component_results.append(
                ComponentResultSummary(
                    component_id=crm.component_id,
                    config_summary=filtered_config,
                    runcontext_summary=filtered_runcontext,
                    outputs_summary=filtered_outputs
                )
            )

        return PipelineResults(
            run_id=run_metadata.run_id,
            component_results=component_results,
            created_at=run_metadata.created_at
        )
