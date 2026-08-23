from dagster import MetadataValue, TableSchema, TableColumn, TableRecord
from typing import Dict, Any, List
import dagster as dg
import statistics


class DagsterMetaDataFactory:
    @staticmethod
    def create_dynamic_table(structured_data: Dict[str, Any]) -> dg.MetadataValue:
        trials = {}
        all_numeric_sub_keys = set()

        # 1. Daten filtern und sammeln
        for key, value in structured_data.items():
            # Wir interessieren uns nur für Trials
            if key.startswith("trial_") and "/" in key:
                parts = key.split("/", 1)
                trial_id = parts[0]
                full_sub_key = parts[1]
                
                # Filter: Nur Zahlen (int/float), aber keine Booleans (da bool ein int-Subtyp ist)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if trial_id not in trials:
                        trials[trial_id] = {"trial_id": trial_id}

                    if isinstance(value, float):
                        # Rundet auf 4 Nachkommastellen für die Tabelle
                        formatted_value = round(value, 6)
                    else:
                        formatted_value = value
                    
                    # Spaltenname kürzen: Nur der letzte Teil (z.B. "accuracy")
                    # Wenn du Duplikate befürchtest, nimm die letzten zwei Teile
                    short_key = full_sub_key.split("/")[-1]
                    
                    trials[trial_id][short_key] = formatted_value
                    all_numeric_sub_keys.add(short_key)

        if not trials:
            return None

        # 2. Schema dynamisch erstellen
        # Wir sortieren die Spalten, damit sie immer in der gleichen Reihenfolge sind
        sorted_keys = sorted(list(all_numeric_sub_keys))
        columns = [TableColumn("trial_id", type="string")]
        
        for sk in sorted_keys:
            # Da wir oben gefiltert haben, wissen wir, dass es Zahlen sind
            # Wir prüfen kurz, ob es irgendwo ein Float ist, sonst nehmen wir int
            is_float = any(isinstance(t.get(sk), float) for t in trials.values())
            columns.append(TableColumn(sk, type="float" if is_float else "integer"))

        # 3. Records erstellen (Wrapper nutzen!)
        table_records = []
        for tid in sorted(trials.keys()):
            # Wir füllen fehlende Werte mit None auf, falls ein Trial einen Key nicht hat
            row_data = {col.name: trials[tid].get(col.name) for col in columns}
            table_records.append(TableRecord(data=row_data))

        return dg.MetadataValue.table(
            records=table_records,
            schema=TableSchema(columns=columns)
        )
    
    
    @staticmethod
    def create(structured_data: Dict[str, Any], aggregate: bool = False) -> Dict[str, MetadataValue]:
        final_meta = {}
        
        if not aggregate:
            # Trial oder flache Daten -> Normales Mapping
            return {k: DagsterMetaDataFactory._map_value(v) for k, v in structured_data.items()}
        
        # Mehrere Trials aggregieren
        # Wir gruppieren die Werte nach ihrem "fachlichen" Key (ohne den Trial-Präfix)
        # Beispiel: 'trial_001/accuracy' und 'trial_002/accuracy' -> 'accuracy': [0.7, 0.8]
        grouped_values: Dict[str, List[float]] = {}
        
        for key, value in structured_data.items():
            if isinstance(value, (int, float)) and "/" in key:
                # Wir schneiden den 'trial_XXX/' Teil ab
                business_key = "/".join(key.split("/")[1:])
                grouped_values.setdefault(business_key, []).append(float(value))

        # Jetzt aggregieren wir die Gruppen auf statische Keys
        for b_key, values in grouped_values.items():
            final_meta[f"agg/{b_key}/max"] = MetadataValue.float(round(float(max(values)), 6))
            final_meta[f"agg/{b_key}/avg"] = MetadataValue.float(round(float(statistics.mean(values)), 6))
            # Optional: Der Wert des besten Trials könnte hier auch stehen

    
        # Füge die dynamische Übersichtstabelle hinzu
        table = DagsterMetaDataFactory.create_dynamic_table(structured_data)
        if table:
            final_meta["trials_overview"] = table
        
        return final_meta

    @staticmethod
    def _map_value(v: Any) -> MetadataValue:
        """Hilfsfunktion für das Typ-Mapping (inkl. Bool-Fix)."""
        if isinstance(v, bool): 
            return MetadataValue.text(str(v))
        if isinstance(v, float): 
            return MetadataValue.float(v)
        if isinstance(v, int): 
            return MetadataValue.int(v)
        return MetadataValue.text(str(v))