#from __future__ import annotations
from ki.bootstrap import all
from pathlib import Path
from multiprocessing import freeze_support

def main() -> None:
    # --- Dagster / Projekt-Imports NUR im main ---
    # (wichtig für Multiprocess + Windows/Linux)
    from dagster import DagsterInstance, execute_job, reconstructable

    # Job-Definition
    from ki_dagster.jobs_ki import node_orchestrator_job

    # Dagster Instance (lokal / Default)
    instance = DagsterInstance.get()


    # "./notebooks/projects/llm_test/configs/node.yaml"
    # Optional: Run-Config (falls du nodes_yaml_path später konfigurierbar machst)
    run_config = {
        "inputs": {
            "nodes_yaml_path": {
                "value": "./notebooks/projects/ml/configs/all_nodes.yaml"
            }
        }
    }

    # --- Job ausführen ---
    with execute_job(
        reconstructable(node_orchestrator_job),
        run_config=run_config,
        instance=instance,
    ) as result:

        if not result.success:
            raise RuntimeError("Dagster job failed")

        # Falls aggregate_results_op ein Output-Handle hat
        results = result.output_for_node("aggregate_results_op")
        print("Final results:", results)


if __name__ == "__main__":
    freeze_support()  # zwingend für Multiprocess
    main()

