from ki.core.nodeorchestrator.yamlloader import load_nodes_from_yaml
from ki.core.nodeexecutor.dataclasses import NodeConfig
from ki.core.nodeexecutor.nodeexecutor import NodeExecutor
from ki.core.datapipeline.datapipeline_dataclasses import PipelineResults
import dagster as dg
from pathlib import Path
from dagster import (
    asset, 
    Definitions, 
    AssetSelection, 
    define_asset_job, 
    Output, 
    AssetExecutionContext
)

# Pfad zu deiner YAML
YAML_PATH = Path("/app/notebooks/projects/ml/configs/all_nodes.yaml")

# 1. Nodes laden
node_configs = load_nodes_from_yaml(YAML_PATH)

# 2. Assets dynamisch generieren (Factory)
def build_assets(configs: list[NodeConfig]):
    assets_list = []
    
    for cfg in configs:
        # Closure, um die Config an das Asset zu binden
        def _make_asset(node_cfg: NodeConfig):
            @asset(
                name=node_cfg.node_id,
                group_name="ml_pipelines",
                key_prefix=["ml"]
            )
            def individual_node_asset(context: AssetExecutionContext):
                context.log.info(f"Running Node: {node_cfg.name}")
                
                executor = NodeExecutor(node_cfg)
                result = executor.run()
                
                # Metadaten für die UI extrahieren
                optuna_base = node_cfg.generator_config.get("optuna_base", {}) if node_cfg.generator_config else {}
                
                return Output(
                    value=result,
                    metadata={
                        "study_name": optuna_base.get("study_name", "N/A"),
                        "metric": optuna_base.get("metric", "N/A"),
                        "trials": optuna_base.get("n_trials", 0)
                    }
                )
            return individual_node_asset

        assets_list.append(_make_asset(cfg))
    return assets_list

generated_assets = build_assets(node_configs)

# 3. Finaler Fan-In (Sammelt alle Ergebnisse)
@asset(deps=generated_assets)
def final_pipeline_report():
    return "All ML Nodes completed successfully."

# 4. Alles bündeln
defs = Definitions(
    assets=[*generated_assets, final_pipeline_report],
    jobs=[define_asset_job("ml_all_nodes_job", selection=AssetSelection.all())]
)