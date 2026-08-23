# Bootstrap zur Befüllung aller Registries
from __future__ import annotations
from ki.bootstrap import all

from ki.core.nodeorchestrator.nodeorchestrator import NodeOrchestrator
from pathlib import Path

# ML
# Alle ML Modelle mit Optuna
#nodes_yaml_path = Path("/app/projects/ml/configs/all_nodes.yaml")

# Nur ein Modell mit Optuna
#nodes_yaml_path = Path("/app/projects/ml/configs/node_randomforest_opt.yaml")
#nodes_yaml_path = Path("/app/projects/ml/configs/node_kerasdense_opt.yaml")

# Ohne Optuna
#nodes_yaml_path = Path("/app/projects/ml/configs/simple_node_xgboost.yaml")
#nodes_yaml_path = Path("/app/projects/ml/configs/simple_node_kerasdense.yaml")

# Analyze Optuna Study
nodes_yaml_path = Path("/app/projects/ml/configs/analyze_studies_node.yaml")

# NLP
#nodes_yaml_path = Path("/app/projects/llm_test/configs/node.yaml")
#nodes_yaml_path = Path("/app/projects/sentiment/configs/node.yaml")

node_orchestrator = NodeOrchestrator(nodes_yaml_path=nodes_yaml_path)
results = node_orchestrator.run()
print(results)

