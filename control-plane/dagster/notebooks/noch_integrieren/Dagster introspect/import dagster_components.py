import dagster.components
import dagster
import dagster.preview
import dagster.components.components
import dagster.components.component.component_loader
import dagster.components.component.component_scaffolder


def pro_scan(module, label):
    print(f"\n--- Deep Scan: {label} ---")
    items = [item for item in dir(module) if not item.startswith("_")]
    for item in items:
        obj = getattr(module, item)
        # Wir zeigen an, ob es eine Klasse ist und woher sie STAMMT
        origin = getattr(obj, "__module__", "unknown")
        print(f" {item:<30} | Origin: {origin}")

# Scan der bekannten Verdächtigen
pro_scan(dagster_components, "Main Package")
pro_scan(dg_dag, "Dagster Subpackage")
pro_scan(dg_dbt, "DBT Subpackage")
pro_scan(dagster, "Main Package: Dagster")