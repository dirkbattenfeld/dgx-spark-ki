import ast
from pathlib import Path
from typing import List, Dict

def extract_class_docstring(code_dir: Path) -> List[Dict[str, str]]:
    """
    Durchläuft ein Verzeichnis rekursiv, extrahiert Python-Klassen, 
    trennt Docstrings vom Code und entfernt Metadaten-Pfade.
    """
    code_dir = Path(code_dir)
    extracted_data = []
    
    # Definierte Muster für zu ignorierende Metadaten/Ordner
    ignore_patterns = ["__", ".ipynb_checkpoints", ".git", ".pytest_cache", "venv", "env"]

    for path in code_dir.rglob('*.py'):
        # Filterung: Ignoriere Pfade mit "__" oder bekannten Metadaten-Ordnern
        if any(pattern in str(path) for pattern in ignore_patterns):
            continue
            
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    source_code = f.read()
                    tree = ast.parse(source_code)
                    
                    # Imports auf Dateiebene extrahieren
                    file_imports = [
                        node for node in tree.body 
                        if isinstance(node, (ast.Import, ast.ImportFrom))
                    ]
                    import_header = "\n".join(ast.unparse(imp) for imp in file_imports)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            # 1. Docstring extrahieren
                            docstring = ast.get_docstring(node) or ""
                            
                            # 2. Docstring aus dem Body entfernen
                            # Wir behalten nur Knoten, die keine reinen String-Konstanten am Anfang sind
                            clean_body = [
                                item for item in node.body 
                                if not (isinstance(item, ast.Expr) and 
                                        isinstance(item.value, (ast.Str, ast.Constant)))
                            ]
                            
                            # Temporäres Setzen des bereinigten Bodys für unparse
                            node.body = clean_body
                            class_code_only = ast.unparse(node)
                            
                            # Zusammenfügen von Imports und bereinigter Klasse
                            full_code = f"{import_header}\n\n{class_code_only}".strip()
                            
                            extracted_data.append({
                                "code": full_code,
                                "docstring": docstring
                            })
                            
            except (UnicodeDecodeError, PermissionError, SyntaxError):
                # Fehlerhafte Dateien oder Kodierungen werden übersprungen
                continue
                
    return extracted_data
