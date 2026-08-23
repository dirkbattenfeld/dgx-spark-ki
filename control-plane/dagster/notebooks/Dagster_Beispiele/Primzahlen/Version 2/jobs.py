# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.18.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
import dagster as dg
from dagster import op, job, In, Out, DynamicOut, DynamicOutput, multiprocess_executor

from ops import node1_partition, node2_prime_check, node3_stat, node4_aggregate


# %%
@job(executor_def=multiprocess_executor)
def test_job():
    partitions= node1_partition()

    node2_results = partitions.map(
        lambda p: node2_prime_check(p)
    )

    node3_stats = node2_results.map(
        lambda r: node3_stat(r)
    )

    node4_aggregate(node3_stats.collect())


# %%
@job(executor_def=multiprocess_executor)
def node_orchestrator_job():
    nodes_yaml_path = "./projects/ml/configs/all_nodes.yaml"  # statisch oder dynamisch
    nodes = load_nodes_op(nodes_yaml_path)
    
    node_results = nodes.map(lambda n: execute_node_op(n))
    
    aggregate_results_op(node_results.collect())
