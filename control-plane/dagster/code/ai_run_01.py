# Bootstrap zur Befüllung aller Registries
from __future__ import annotations
from ki.bootstrap import all

from ki.core.nodeorchestrator.nodeorchestrator import NodeOrchestrator
from pathlib import Path

#nodes_yaml_path = Path("/app/projects/rag/configs/node_ingestion.yaml")
nodes_yaml_path = Path("/app/projects/rag_request/configs/node_request_fastapi.yaml")

node_orchestrator = NodeOrchestrator(nodes_yaml_path=nodes_yaml_path)
results = node_orchestrator.run()

