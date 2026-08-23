from ki_dagster.ops_ki import load_nodes_op, execute_node_op, aggregate_results_op 
import dagster as dg
from dagster import op, job, In, Out, DynamicOut, DynamicOutput, multiprocess_executor

@job(executor_def=multiprocess_executor)
def node_orchestrator_job(nodes_yaml_path: str):

    nodes = load_nodes_op(nodes_yaml_path)
    
    node_results = nodes.map(lambda n: execute_node_op(n))
    
    aggregate_results_op(node_results.collect())
