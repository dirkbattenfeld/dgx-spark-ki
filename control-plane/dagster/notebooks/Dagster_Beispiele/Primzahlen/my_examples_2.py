from multiprocessing import freeze_support
if __name__ == "__main__":
    freeze_support()
    from ki_dagster.jobs import test_job
    from dagster import DagsterInstance, execute_job, job, reconstructable

    instance = DagsterInstance.get()
    run_config={"ops": {"node1_partition": {"inputs": {"n": {"value": 100000}, "p": {"value": 3}}}}}
    with execute_job(reconstructable(test_job),run_config=run_config, instance=instance) as result:
        agg_result = result.output_for_node("node4_aggregate")
        
    print("Result of Job: ", agg_result)    