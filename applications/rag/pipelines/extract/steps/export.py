import os
from typing import Any

from applications.rag.pipelines.extract.configs import ExportConfig
from applications.rag.pipelines.extract.models import AggregatedResult
from libs.streampipe.observability import trace_action


@trace_action(step_name="export_excel")
async def export_excel_action(
    input_data: AggregatedResult,
    storage_client: Any,
    config: ExportConfig
) -> AggregatedResult:
    """
    Action: Exportiert das aggregierte DataFrame als Excel-Datei (.xlsx) in den S3-Bucket.
    Tauscht die Dateiendung '.docling.chunks.json' gegen die konfigurierte Excel-Endung aus.
    """
    source_path = input_data.source_path
    if not source_path:
        print("⚠️ [Export] Kein source_path im AggregatedResult vorhanden. Export abgebrochen.")
        input_data.status = "error"
        input_data.extras["export_error"] = "No source_path provided in AggregatedResult"
        return input_data

    # Pfadmanipulation: Tausche '.docling.chunks.json' gegen die neue Endung
    suffix_to_replace = ".docling.chunks.json"
    if source_path.endswith(suffix_to_replace):
        target_path = source_path[:-len(suffix_to_replace)] + config.target_extension
    else:
        # Fallback falls die Dateiendung abweicht (z.B. nur .json oder .yaml)
        base_path, _ = os.path.splitext(source_path)
        target_path = base_path + config.target_extension

    print(f"💾 [Export] Starte Excel-Export nach: {target_path}...")

    if input_data.data.empty:
        print("⚠️ [Export] DataFrame ist leer. Erzeuge eine leere Excel-Datei mit Spalten.")

    try:
        # Wir nutzen den storage_client.open Kontextmanager im Binärmodus ("wb")
        # Das fsspec-Dateiobjekt wird direkt an Pandas übergeben
        with storage_client.open(target_path, mode="wb") as f:
            input_data.data.to_excel(f, index=False, engine="openpyxl")
            
        print("✅ [Export] Excel-Datei erfolgreich exportiert.")
        input_data.extras["exported_to"] = target_path
        
    except Exception as e:
        print(f"❌ [Export] Fehler beim Schreiben der Excel-Datei: {e}")
        input_data.status = "error"
        input_data.extras["export_error"] = str(e)
        
    return input_data