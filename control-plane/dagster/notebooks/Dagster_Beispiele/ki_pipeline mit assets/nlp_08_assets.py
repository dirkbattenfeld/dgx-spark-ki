import sys
import os
from multiprocessing import freeze_support
from dagster import materialize, DagsterInstance

# Sicherstellen, dass das Paket ki_dagster gefunden wird
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ki_dagster.definitions_ki import defs

from ki.bootstrap import all

def main():
    # Wir filtern nur die eigentlichen Asset-Definitionen heraus
    # (Dagster hält in defs.assets auch andere Objekte bereit)
    asset_list = [a for a in defs.assets if not isinstance(a, list)]
    
    print(f"Gefundene Nodes in YAML: {len(asset_list) - 1}") # -1 wegen final_report

    # Materialisierung starten
    instance = DagsterInstance.get()
    result = materialize(
        assets=asset_list,
        instance=instance
    )

    if result.success:
        print("\n--- ERFOLG ---")
        print("Alle Assets wurden erfolgreich materialisiert.")
    else:
        print("\n--- FEHLER ---")

if __name__ == "__main__":
    freeze_support()
    main()