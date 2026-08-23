from ki.core.nodeorchestrator.yamlloader import load_nodes_from_yaml
from ki.core.nodeexecutor.dataclasses import NodeConfig
from ki.core.nodeexecutor.nodeexecutor import NodeExecutor
from ki.core.datapipeline.datapipeline_dataclasses import PipelineResults
import dagster as dg
from dagster import op, job, In, Out, DynamicOut, DynamicOutput, multiprocess_executor
from pathlib import Path

@op(out=DynamicOut())
def load_nodes_op(nodes_yaml_path: str):
    nodes = load_nodes_from_yaml(Path(nodes_yaml_path))
    if not nodes:
        raise ValueError(f"No nodes found in YAML {nodes_yaml_path}")

    for i, node in enumerate(nodes):
        yield DynamicOutput(
            value=node,
            mapping_key=f"node_{i}",
        )

@op(ins={"node": In(NodeConfig)}, out=Out(list[PipelineResults]))
def execute_node_op(node: NodeConfig) -> list[PipelineResults]:
    executor = NodeExecutor(node)
    result: list[PipelineResults] = executor.run()
    return result

@op(ins={"results": In(list[list[PipelineResults]])}, out=Out(list[list[PipelineResults]]))
def aggregate_results_op(results: list[list[[PipelineResults]]]) -> list[list[PipelineResults]]:
    return results
