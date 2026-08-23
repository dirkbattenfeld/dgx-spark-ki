# ki/core/nodeorchestrator/nodeorchestrator.py

from ki.core.nodeorchestrator.yamlloader import load_nodes_from_yaml
from ki.core.nodeexecutor.nodeexecutor import NodeExecutor

from pathlib import Path

class NodeOrchestrator:
    """
    todo
    """

    def __init__(self, nodes_yaml_path: Path):
        """
        todo
        """
        nodes_yaml_path = Path(nodes_yaml_path)
        
        # NodeConfig laden
        #todo: Hier nur das reine Laden der Config und das übersetzen in NodeConfig aus 
        #load_nodes_from_yaml herausziehen und in NodeFactory auslagern.
        #Dort die NodeConfig in validierte NodeSpecs übersetzen
        #die dann an den NodeExecutor weitergegeben werden / bereits optimieren für dagster
        #Typen in NodeConfig überarbeiten mit Interface zur Trennung der Layer
        self.run_nodes, self.debug_mode = load_nodes_from_yaml(nodes_yaml_path)
        if not self.run_nodes:
            raise ValueError(f"No nodes found in YAML {nodes_yaml_path}")
        
    def run(self):
        results = []
        for node in self.run_nodes:
            node_executor = NodeExecutor(node)
            result = node_executor.run()
            results.append(result)
        return results
