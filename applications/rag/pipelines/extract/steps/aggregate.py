import json
import re
from typing import Any, Dict, Tuple

import pandas as pd

from applications.rag.pipelines.extract.configs import AggregateConfig
from applications.rag.pipelines.extract.models import AggregatedResult, AggregationInput, ExtractedRecord
from libs.streampipe.observability import trace_action


def prep_extract_to_aggregation(
    input_data: Any,  # Das ExtractResult aus dem vorherigen Pipeline-Schritt
    global_payload: Dict[str, Any]
) -> Tuple[AggregationInput, None]:
    """
    Hook zur Formatkonvertierung: Überführt das spezifische 'ExtractResult' 
    in das generische 'AggregationInput'. Übernimmt die Bereinigung und das 
    Sicherheits-Parsing der unstrukturierten LLM-Antworten.
    
    Signatur ist vollkompatibel mit dem PipelineRunner: (input_data, global_payload) -> (input_data, overrides)
    """
    extracted_records = []
    source_path = getattr(input_data, "source_path", "")
        
    # Iteration über alle extrahierten Chunks
    for extraction in input_data.extractions:
        raw_output = extraction.raw_llm_output.strip()
        
        # Sicherer Schutz vor Markdown-Codeblocks (```json ... ``` oder ```yaml ... ```)
        # Um Parser-Konflikte im Pipeline-System zu vermeiden, bauen wir die Backticks dynamisch
        backticks = "`" * 3
        if backticks in raw_output:
            pattern = rf"{backticks}(?:json|yaml)?\s*([\s\S]*?)\s*{backticks}"
            blocks = re.findall(pattern, raw_output)
            if blocks:
                raw_output = blocks[0].strip()
        
        # Leere Arrays oder leere Antworten direkt überspringen
        if not raw_output or raw_output == "[]":
            continue
            
        try:
            parsed_data = json.loads(raw_output)
            
            # Sicherstellen, dass das Ergebnis eine Liste von Dictionaries ist
            records_list = parsed_data if isinstance(parsed_data, list) else [parsed_data]
            
            for item in records_list:
                if not isinstance(item, dict):
                    continue
                
                # Datensatz für die Aggregation vorbereiten
                extracted_records.append(
                    ExtractedRecord(
                        data=item,
                        parent_id=extraction.parent_id,
                        page_numbers=extraction.page_numbers
                    )
                )
        except json.JSONDecodeError as e:
            # Fehler abfangen, damit unvollständige LLM-Antworten nicht die Pipeline blockieren
            print(f"⚠️ Parsing-Fehler bei Chunk {extraction.parent_id}: {e}")
            
    # AggregationInput mit den gesammelten Records erstellen
    agg_input = AggregationInput(
        records=extracted_records,
        source_path = source_path
    )
    
    # Rückgabe des neuen Inputs und None für die Overrides
    return agg_input, None


# --- Die aggregate_action ---

@trace_action(step_name="aggregate")
async def aggregate_action(
    input_data: AggregationInput, 
    config: AggregateConfig
) -> AggregatedResult:
    """
    Action: Fusioniert die extrahierten Datensätze zu einer flachen Struktur,
    führt eine Deduplizierung basierend auf den in der Config definierten Keys aus
    und liefert ein strukturiertes AggregatedResult mit dem Pandas DataFrame zurück.
    """
    if not input_data.records:
        print("⚠️ Keine Datensätze zur Aggregation übergeben.")
        return AggregatedResult(
            data=pd.DataFrame(),
            row_count=0,
            status="empty",
            extras={"message": "No input records provided"}
        )
        
    # 1. Erstellen einer flachen Liste für Pandas
    flat_rows = []
    for record in input_data.records:
        # Verschmelzen der extrahierten Nutzdaten mit Herkunfts-Metadaten
        row = {**record.data}
        row["_parent_id"] = record.parent_id
        row["_page_numbers"] = ",".join(str(p) for p in record.page_numbers)
        flat_rows.append(row)
        
    df = pd.DataFrame(flat_rows)
    initial_len = len(df)
    duplicates_removed = 0
    
    # 2. Intelligente Deduplizierung basierend auf den konfigurierten Keys der Config
    active_keys = [k for k in config.dedup_keys if k in df.columns]
    
    if active_keys:
        # Wir behalten den ersten Treffer (keep='first'), da dieser logisch weiter vorne im Dokument steht
        df = df.drop_duplicates(subset=active_keys, keep="first")
        duplicates_removed = initial_len - len(df)
        if duplicates_removed > 0:
            print(f"🧹 Deduplizierung aktiv (Keys: {active_keys}): {duplicates_removed} Duplikate entfernt.")
            
    # 3. Strukturierte Rückgabe verpackt in das standardisierte Pydantic-Ergebnis
    pipeline_metrics = {
        "initial_row_count": initial_len,
        "duplicates_removed": duplicates_removed,
        "dedup_keys_used": active_keys
    }
    
    source_path = getattr(input_data, "source_path", "")
     
    return AggregatedResult(
        data=df,
        row_count=len(df),
        source_path=source_path,
        status="success",
        extras=pipeline_metrics
    )