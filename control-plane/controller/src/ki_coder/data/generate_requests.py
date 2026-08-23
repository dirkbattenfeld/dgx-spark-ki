import yaml
from pathlib import Path

def generate_requests(extracted_data: list, output_path: Path):
    """
    Transformiert die extrahierten Daten in das Ziel-Template 
    und speichert sie als YAML-Datei.
    """
    yaml_entries = []
    
    for i, entry in enumerate(extracted_data, start=1):
        # Mapping auf dein Template
        item = {
            "id": i,
            "prompt_type": "docstring_expert",
            "use_context": False,
            "request": entry["code"],
            "docstring_original": entry["docstring"]
        }
        yaml_entries.append(item)

    # Konfiguration für sauberes YAML-Format (Block-Style für Code-Blöcke)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            yaml_entries, 
            f, 
            allow_unicode=True, 
            sort_keys=False, 
            default_flow_style=False,
            width=1000  # Verhindert ungewollte Zeilenumbrüche im Code
        )
