# ki/core/datapipeline/resultprojector.py

from ki.core.datapipeline.datapipeline_dataclasses import PipelineResults, RunMetaData, ComponentResultSummary
from ki.core.pipelineresult.projector.registry import projector_registry
import logging
from typing import Optional

@projector_registry.register("complete")
class CompletePipelineResultProjector:
    """
    Implementiert das Interface für den Persistor.
    Key: 'complete' -> Extrahiert alle relevanten Daten gemäß Metadata-Regeln.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def project(self, run_metadata: RunMetaData) -> PipelineResults:
        self.logger.debug(f"Projecting complete results for run {run_metadata.run_id}")

        component_results = []

        for crm in run_metadata.component_runs:
            filtered_outputs = {}
            for attr_name, attr_info in crm.outputs_summary.items():
                # Fachliche Logik: Nur behalten, was nicht explizit gedroppt wurde
                # und mindestens eine der Relevanz-Bedingungen erfüllt
                if attr_info.get("drop"):  # Attribute aus Droplist werden auch bei complete gederoppt
                    continue

                if (attr_info.get("inline") or
                    attr_info.get("pipeline_output") or
                    attr_info.get("write_artifact")):
                    filtered_outputs[attr_name] = attr_info["value"]

            component_results.append(
                ComponentResultSummary(
                    component_id=crm.component_id,
                    input_refs=crm.input_refs,
                    config_summary=crm.config_summary,
                    runcontext_summary=crm.runcontext_summary,
                    outputs_summary=filtered_outputs,
                    artifacts=crm.artifacts,
                )
            )

        return PipelineResults(
            run_id=run_metadata.run_id,
            component_results=component_results,
            created_at=run_metadata.created_at
        )
