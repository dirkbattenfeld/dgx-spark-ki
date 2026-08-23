import json
import re
from pathlib import Path

def clean_markdown(code: str) -> str:
    """Entfernt Markdown-Code-Blocks (```python ... ```)."""
    return re.sub(r'^```python\n|```$', '', code, flags=re.MULTILINE).strip()

def extract_main_docstring(code: str) -> str:
    """
    Extrahiert den Klassen-Docstring aus dem Code-Block, 
    um ihn als Instruction-Basis zu nutzen.
    """
    try:
        import ast
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node)
                if doc:
                    return doc
    except SyntaxError:
        pass
    return "Implementiere die Klasse basierend auf der Architektur."

def generate_sft_data(jsonl_path: Path, output_path: Path = None, only_valid: bool = False):
    """
    Transformiert Inferenz-Ergebnisse in SFT-Paare und speichert diese optional als JSONL.
    """
    jsonl_path = Path(jsonl_path)
    sft_dataset = []
    
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
                
            data = json.loads(line)
            
            # Optionaler Qualitätscheck: Überspringe Einträge mit Validierungsfehlern
            if only_valid and data.get("validation_errors"):
                continue
            
            # 1. Den generierten Code aus der Response säubern
            full_response_code = clean_markdown(data["response"])
            
            # 2. Den Docstring als 'Anweisung' extrahieren
            docstring = extract_main_docstring(full_response_code)
            
            # 3. SFT-Paar erstellen
            sft_entry = {
                "instruction": f"Implementiere eine Python-Klasse basierend auf dieser Spezifikation:\n\n{docstring}",
                "content": full_response_code
            }
            sft_dataset.append(sft_entry)
            
    # Speichern der Daten, falls ein Output-Pfad angegeben wurde
    if output_path:
        output_path = Path(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            for entry in sft_dataset:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[OK] {len(sft_dataset)} SFT-Datensätze nach {output_path} geschrieben.")
            
    return sft_dataset
