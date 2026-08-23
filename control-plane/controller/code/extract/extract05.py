import os
import json
import pandas as pd
from ki_dgxsdk.ki_sdk import DGX_Client

# ==============================================================================
# 1. ZENTRALE KONFIGURATION (Erweitert um Chunks-Modus & Validierungs-Felder)
# ==============================================================================
CONFIGSETS = {
    "emissionen_json": {
        "context_file_path": "/app/projects/extract/data/Nachhaltigkeitsberichte/2024-Henkel.tables.json",
        "prompt": (
            "Extrahiere alle Kennzahlen zu Treibhausgasemissionen (THG) von Henkel für die Jahre 2021 und 2024.\n" 
            "Wenn Kennzahlen zu Emissionen aufgegliedert werden, dann nehme alle Positionen der Untergliederung in deinen Output auf.\n"
            "Wenn Du zu einer Kennzahl keinen Wert findest, dann setze den wert auf 'NA'.\n"
            "Jedes Objekt im Array muss folgende Felder haben: 'jahr', 'bezeichnung' (inkl. Geltungsbereich) und 'wert' (als Zahl ohne Tausendertrennpunkt oder bei Prozentzahlen mit Komma)."
        ),
        "temperature": 0.0,
        "max_characters": 350000,
        "context_type": "json",
        "value_field": "wert"  # Definiert das Werte-Feld für die Widerspruchs-Validierung
    },
    "emissionen_md": {
        "context_file_path": "/app/projects/extract/data/Nachhaltigkeitsberichte/2024-Henkel.md",
        "prompt": (
            "Extrahiere alle Kennzahlen zu Treibhausgasemissionen (THG) von Henkel für die Jahre 2021 und 2024.\n" 
            "Wenn Kennzahlen zu Emissionen aufgegliedert werden, dann nehme alle Positionen der Untergliederung in deinen Output auf.\n"
            "Wenn Du zu einer Kennzahl keinen Wert findest, dann setze den wert auf 'NA'.\n"
            "Jedes Objekt im Array muss folgende Felder haben: 'jahr', 'bezeichnung' (inkl. Geltungsbereich) und 'wert' (als Zahl ohne Tausendertrennpunkt oder bei Prozentzahlen mit Komma)."
        ),
        "temperature": 0.0,
        "max_characters": 350000,
        "context_type": "markdown",
        "value_field": "wert"
    },
    # NEU: Modus 3 lädt die Ausgabe des vorangegangenen Hierarchie-Chunking Endpunkts
    "emissionen_chunks": {
        "context_file_path": "/app/projects/extract/data/Nachhaltigkeitsberichte/2024-Telekom.docling.chunks.json",
        "prompt": (
            "Extrahiere alle Kennzahlen für alle Jahre aus den bereitgestellten Daten.\n" 
            "Wenn Kennzahlen aufgegliedert werden, dann nehme alle Positionen der Untergliederung in deinen Output auf.\n"
            "Gebe nur Kennzahlen aus, für die Du in den bereitgestellten Daten einen numerischen Wert findest.\n"
            "Jedes Objekt im Array muss folgende Felder haben: 'jahr', 'bezeichnung' (inkl. Geltungsbereich) und 'wert' (als Zahl ohne Tausendertrennpunkt oder bei Prozentzahlen mit Komma)."
        ),
        "temperature": 0.0,
        "max_characters": 350000,
        "context_type": "chunks",
        "value_field": "wert"
    },
    "iu": {
        "context_file_path": "/app/projects/extract/data/iu/Kraemer_Lukas.pdf.md",
        "prompt": (
            "Extrahiere Name, Matrikelnummer/Enrollment, Titel, Studiengang/studyprogramm und Sprache der Arbeit. "
            "Jedes Objekt im Array muss folgende Felder haben: 'name', 'matrikelnummer', 'studiengang', 'titel', 'sprache'. "
            "Erzeuge keinen erklärenden Text vor oder nach dem JSON."
        ),
        "temperature": 0.0,
        "max_characters": 350000,
        "context_type": "markdown",
        "value_field": "matrikelnummer"
    }
}

# ==============================================================================
# 2. LOGIK-FUNKTIONEN
# ==============================================================================

def load_context(file_path: str, max_characters: int) -> str:
    """
    Prüft das Dateiformat automatisch. Lädt und formatiert den Kontext 
    entsprechend (JSON-Tabellen-Strukturierung vs. Plain-Text/Markdown).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Die Datei wurde nicht gefunden unter: {file_path}")

    if file_path.lower().endswith('.json'):
        print(f"-> JSON-Format erkannt. Starte strukturierte Tabellen-Extraktion für {os.path.basename(file_path)}...")
        with open(file_path, "r", encoding="utf-8") as f:
            tables_data = json.load(f)
        
        prepared_lines = []
        for table_id, table_info in tables_data.items():
            prepared_lines.append(f"--- Tabelle: {table_id} (Seite {table_info.get('page_index', 'Unbekannt')}) ---")
            prepared_lines.append(json.dumps(table_info["data"], ensure_ascii=False))
            prepared_lines.append("") 
        
        document_content = "\n".join(prepared_lines)
    else:
        print(f"-> Standard-Textformat erkannt für {os.path.basename(file_path)}...")
        with open(file_path, "r", encoding="utf-8") as f:
            document_content = f.read()

    truncated_content = document_content[:max_characters]
    print(f"   Originale Länge: {len(document_content)} Zeichen | Gekürzte Länge: {len(truncated_content)} Zeichen")
    
    return truncated_content


def build_system_prompt(context: str, context_type: str) -> str:
    """Erstellt den dynamischen System-Prompt."""
    return (
        f"Du bist ein Spezialist für die Extraktion von Daten aus {context_type}.\n"
        f"Beantworte die Fragen des Benutzers AUSSCHLIESSLICH auf Basis der unten bereitgestellten {context_type}.\n"
        "Gib die Daten AUSSCHLIESSLICH als valides JSON-Array zurück.\n"
        "Erzeuge keinen erklärenden Text vor oder nach dem JSON.\n\n"
        f"--- START {context_type.upper()} ---\n"
        f"{context}\n"
        f"--- ENDE {context_type.upper()} ---"
    )


def extract_data(context: str, context_type: str, prompt: str, temperature: float) -> list:
    """
    ZENTRALE EXTRAKTIONS-LOGIK (Keine Code-Redundanz):
    Verbindet sich mit dem vLLM-Server, setzt Prompts ab und parst das Ergebnis sicher als JSON-Liste.
    """
    system_prompt = build_system_prompt(context, context_type)
    
    response = vllm.call(
        prompt = prompt,
        system_prompt = system_prompt,
        temperature = temperature  
    )
    
    text = response['choices'][0]['message']['content'].strip()
    
    # Säuberung von potentiellen LLM Markdown-Code-Blöcken (```json ... ```)
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text) if text else []
    except json.JSONDecodeError:
        # Fallback bei unvollständigen/beschädigten JSON-Outputs einzelner Chunks
        print(f"   [WARNUNG] JSON-Parsing fehlgeschlagen für Kontext-Typ '{context_type}'.")
        return []


def validate_dataframe(df: pd.DataFrame, value_field: str) -> pd.DataFrame:
    """
    Validiert den finalen fusionierten DataFrame auf Duplikate und logische Widersprüche.
    """
    if df.empty:
        print("\n[VALIDIERUNG] DataFrame ist leer. Keine Validierung möglich.")
        return df

    print("\n=== Starte Daten-Validierung ===")
    
    # a. Duplikate ermitteln, loggen und bereinigen
    duplicate_mask = df.duplicated(keep='first')
    total_duplicates = duplicate_mask.sum()
    
    if total_duplicates > 0:
        print(f"-> [BESEITIGUNG] {total_duplicates} exakte Duplikate gefunden und entfernt:")
        print(df[df.duplicated(keep=False)].sort_values(by=list(df.columns)))
        df = df.drop_duplicates(keep='first').reset_index(drop=True)
    else:
        print("-> [OK] Keine exakten Duplikate im Datensatz enthalten.")

    # b. Widersprüchliche Einträge prüfen
    if value_field and value_field in df.columns:
        # Gruppierungs-Schlüssel sind alle Spalten außer dem Value-Feld selbst
        key_columns = [col for col in df.columns if col != value_field]
        
        if key_columns:
            # Zeilen filtern, die dieselben Schlüssel besitzen, aber variierende Werte im Value-Feld aufweisen
            contradictions = df.groupby(key_columns).filter(lambda x: x[value_field].nunique() > 1)
            
            if not contradictions.empty:
                print(f"-> [WARNUNG] {len(contradictions)} widersprüchliche Einträge für '{value_field}' identifiziert:")
                print(contradictions.sort_values(by=key_columns))
            else:
                print(f"-> [OK] Keine logischen Widersprüche bezüglich Feld '{value_field}' detektiert.")
    else:
        print(f"-> [INFO] Überspringe Widerspruchsprüfung (Feld '{value_field}' nicht im DataFrame vorhanden oder definiert).")
        
    return df

def save_dataframe(df: pd.DataFrame, source_file_path: str) -> None:
    """
    ZENTRALE PERSISTIERUNGS-LOGIK:
    Speichert den bereinigten DataFrame als CSV (optimiert für VS Code DataWrangler)
    und als Excel-Datei für die manuelle Durchsicht.
    """
    if df.empty:
        print("\n[SPEICHERUNG] DataFrame ist leer. Export abgebrochen.")
        return

    print("\n=== Starte Daten-Persistierung ===")

    # Basis-Pfad dynamisch ermitteln (entfernt Endungen wie .chunks.json, .tables.json oder .md)
    base_path, _ = os.path.splitext(source_file_path)
    if base_path.endswith('.chunks'):
        base_path = base_path.rsplit('.chunks', 1)[0]
    elif base_path.endswith('.tables'):
        base_path = base_path.rsplit('.tables', 1)[0]

    csv_output_path = f"{base_path}.extracted.csv"
    xlsx_output_path = f"{base_path}.extracted.xlsx"

    # 1. CSV-Export (sep=';' und utf-8-sig garantieren fehlerfreie Umlaute im DataWrangler und Excel)
    df.to_csv(csv_output_path, sep=';', index=False, encoding='utf-8-sig')
    print(f"-> [ERFOLGREICH] CSV exportiert für DataWrangler: {csv_output_path}")

    # 2. Excel-Export
    try:
        df.to_excel(xlsx_output_path, index=False, engine='openpyxl')
        print(f"-> [ERFOLGREICH] Excel exportiert: {xlsx_output_path}")
    except ImportError:
        print("-> [INFO] Excel-Export übersprungen, da 'openpyxl' nicht installiert ist (pip install openpyxl).")
        

def run_pipeline(config_name: str, config: dict) -> pd.DataFrame:
    """
    Führt die Extraktions-Pipeline aus, validiert die Daten und gibt 
    den finalen DataFrame zurück. Keine Vermischung mit der Speicherung.
    """
    print(f"\n=== Starte Pipeline-Lauf: {config_name} ===")
    file_path = config["context_file_path"]
    context_type = config.get("context_type", "markdown")
    
    collected_dfs = []
    final_df = pd.DataFrame() # Fallback, falls nichts gefunden wird

    try:
        # MODUS 3: Iterativer Chunks-Modus
        if context_type == "chunks":
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Die Chunks-Datei wurde nicht gefunden unter: {file_path}")
                
            print(f"-> Chunks-Hierarchie erkannt. Lade Struktur aus {os.path.basename(file_path)}...")
            with open(file_path, "r", encoding="utf-8") as f:
                chunks_data = json.load(f)
            
            parents = chunks_data.get("parents", [])
            print(f"   Iteriere über {len(parents)} Parent-Chunks zur Extraktion...")
            
            for parent in parents:
                parent_id = parent.get("parent_id", "Unbekannt")
                parent_text = parent.get("text", "")
                
                if not parent_text.strip():
                    continue
                
                truncated_parent_text = parent_text[:config["max_characters"]]
                
                extracted_records = extract_data(
                    context=truncated_parent_text,
                    context_type=config["context_type"],
                    prompt=config["prompt"],
                    temperature=config["temperature"]
                )
                
                print(f"   [Parent: {parent_id}] -> {len(extracted_records)} JSON-Datensätze extrahiert.")
                
                if extracted_records:
                    collected_dfs.append(pd.DataFrame(extracted_records))

        # MODUS 1 & 2: Klassische Single-File Extraktion (JSON / Markdown)
        else:
            context = load_context(file_path, config["max_characters"])
            extracted_records = extract_data(
                context=context,
                context_type=context_type,
                prompt=config["prompt"],
                temperature=config["temperature"]
            )
            if extracted_records:
                collected_dfs.append(pd.DataFrame(extracted_records))

        # DataFrames fusionieren und validieren
        if collected_dfs:
            combined_df = pd.concat(collected_dfs, ignore_index=True)
            final_df = validate_dataframe(combined_df, config.get("value_field"))
            
            print("\n=== Finaler, validierter DataFrame ===")
            print(final_df)
        else:
            print("\n[INFO] Es konnten aus keinem Abschnitt Datensätze extrahiert werden.")

    except Exception as e:
        print(f"\nFehler beim Pipeline-Lauf: {e}")
        
    return final_df


# ==============================================================================
# 3. MAIN-STEUERUNG
# ==============================================================================
if __name__ == "__main__":
    sdk = DGX_Client(config_path="/app/code/microservices.yaml")
    vllm = sdk.get_client("vllm")
    
    # Switch: "emissionen_json", "emissionen_md", "emissionen_chunks" oder "iu"
    target_config = "emissionen_chunks"
    
    if target_config in CONFIGSETS:
        run_config = CONFIGSETS[target_config]
        
        # 1. Pipeline ausführen und Daten generieren/validieren
        result_df = run_pipeline(target_config, run_config)
        
        # 2. Absolut getrennte Speicherung am Ende des Gesamtprozesses
        if not result_df.empty:
            save_dataframe(result_df, run_config["context_file_path"])
        else:
            print("\n[MAIN] Speicherprozess übersprungen, da keine Daten generiert wurden.")
            
    else:
        print(f"Konfiguration '{target_config}' existiert nicht.")
    