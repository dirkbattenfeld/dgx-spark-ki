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

#from resources import MyAssetConfig

import dagster as dg

class MyAssetConfig(dg.Config):
    person_name: str

@dg.definitions
def resources() -> dg.Definitions:
    return dg.Definitions(resources={"config": MyAssetConfig(person_name="")})
    
@dg.asset
def greeting(config: MyAssetConfig) -> str:
    return f"hello {config.person_name}"


asset_result = dg.materialize(
    [greeting],
    run_config=dg.RunConfig({"greeting": MyAssetConfig(person_name="Alice")}),
)

print(asset_result)

# %%
import dagster as dg

class UserData(dg.Config):
    age: int
    email: str
    profile_picture_url: str

class MyNestedConfig(dg.Config):
    user_data: dict[str, UserData]

@dg.asset
def average_age(config: MyNestedConfig): ...

result = dg.materialize(
    [average_age],
    run_config=dg.RunConfig(
        {
            "average_age": MyNestedConfig(
                user_data={
                    "Alice": UserData(
                        age=10,
                        email="alice@gmail.com",
                        profile_picture_url="...",
                    ),
                    "Bob": UserData(
                        age=20,
                        email="bob@gmail.com",
                        profile_picture_url="...",
                    ),
                }
            )
        }
    ),
)

# %%
import dagster as dg
from dagster import op, job, In, Out, DynamicOut, DynamicOutput

@op(out=DynamicOut())
def node1_partition(n: int, p: int):
    """
    Für jedes m = 1 .. p-1:
    - erzeuge die ersten n Zahlen >= 2, die kongruent m mod p sind
    - yield als eigener DynamicOutput mit mapping_key = part_{m}
    """
    
    for m in range(1, p):
        part: List[int] = []

        k = 0
        while len(part) < n:
            candidate = m + k * p
            if candidate >= 2:
                part.append(candidate)
            k += 1

        yield DynamicOutput(
            value=part,
            mapping_key=f"part_{m}",
        )

@job
def test_job():
    node1_partition()

result = test_job.execute_in_process(
    run_config={"ops": {"node1_partition": {"inputs": {"n": {"value": 100}, "p": {"value": 13}}}}})


# %%
import dagster as dg
from dagster import op, job, In, Out, DynamicOut, DynamicOutput, multiprocess_executor
from dataclasses import dataclass
from typing import List, Tuple, Optional
from collections import defaultdict

import math
import numpy as np

# ---------------------------
# SPECS / RESULTS
# ---------------------------

@dataclass
class Node1Spec:
    n: int
    p: int

@dataclass
class Node2Spec:
    use_numpy: bool = False

@dataclass
class Node2Result:
    value: int
    is_prime: bool

@dataclass
class Node3Spec:
    use_numpy: bool = False
    binwidth: int = 1000
    mode: str = "per_partition"

from typing import Dict

@dataclass
class Node3Result:
    counts: Dict[int, int]   

# NODE 1: Partitionierung + Fan-Out
@op(out=DynamicOut())
def node1_partition(n: int, p: int):
    """
    Für jedes m = 1 .. p-1:
    - erzeuge die ersten n Zahlen >= 2, die kongruent m mod p sind
    - yield als eigener DynamicOutput mit mapping_key = part_{m}
    """
    
    for m in range(1, p):
        part: List[int] = []

        k = 0
        while len(part) < n:
            candidate = m + k * p
            if candidate >= 2:
                part.append(candidate)
            k += 1

        yield DynamicOutput(
            value=part,
            mapping_key=f"part_{m}",
        )
        
# NODE 2: Primzahlenprüfung
@op
def node2_prime_check(partition: List[int]) -> List[Node2Result]:
    use_numpy = False
    results = []
    for num in partition:
        if num < 2:
            results.append(Node2Result(num, False))
            continue
        prime = True
        for i in range(2, int(math.isqrt(num)) + 1):
            if num % i == 0:
                prime = False
                break
        results.append(Node2Result(num, prime))
    if use_numpy:
        results = np.array(results)
    return results


# NODE 3: Statistik / Binning
@op
def node3_stat(partition_results: List[Node2Result]) -> Node3Result:

    binwidth = 10
    counts = defaultdict(int)

    for r in partition_results:
        if r.is_prime:
            idx = r.value // binwidth
            counts[idx] += 1

    return Node3Result(counts=dict(counts))


# NODE 4: Aggregation
@op
def node4_aggregate(stats_list: List[Node3Result]) -> Node3Result:
    agg = defaultdict(int)

    for stats in stats_list:
        for idx, cnt in stats.counts.items():
            agg[idx] += cnt

    return Node3Result(counts=dict(agg))


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
from jobs import test_job

result = test_job.execute_in_process(
    run_config={"ops": {"node1_partition": {"inputs": {"n": {"value": 100}, "p": {"value": 3}}}}})

agg_result = result.output_for_node("node4_aggregate")
print(result)


# %%
from jobs import test_job
from dagster import DagsterInstance, execute_job, job, reconstructable

instance = DagsterInstance.get()
run_config={"ops": {"node1_partition": {"inputs": {"n": {"value": 100000}, "p": {"value": 3}}}}}
with execute_job(reconstructable(test_job),run_config=run_config, instance=instance) as result:
    agg_result = result.output_for_node("node4_aggregate")
    
print("Result of Job: ", agg_result)    

# %%
