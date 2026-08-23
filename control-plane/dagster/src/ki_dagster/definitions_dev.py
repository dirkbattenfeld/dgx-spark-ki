import dagster as dg
from pathlib import Path
from dagster.components import build_component_defs

import sys
import os

#import debugpy
#if not debugpy.is_client_connected():
#    try:
#        print("Debug-Mode aktiv. Warte auf VS Code...")
#        debugpy.listen(("0.0.0.0", 5678))
#        print("Bitte jetzt Debugging mit F5 starten!")
#        debugpy.wait_for_client()
#        # Expliziter Breakpoint direkt nach dem Verbinden
#        debugpy.breakpoint()
#    except Exception as e:
#        print(f"Debugger-Fehler: {e}")

# --- 1. BOOTSTRAP & PFADE ---
# Den Root-Pfad so setzen, dass 'ki' und 'ki_dagster' gefunden werden
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT / "src"))

# Dein Framework initialisieren (Registry, Plugins etc.)
try:
    from ki.bootstrap import all
except ImportError as e:
    print(f"BOOTSTRAP ERROR: Konnte ki.bootstrap nicht laden. Pfad: {sys.path}")
    raise e

# Pfad zu deinem Komponenten-Instanz-Ordner (wo die yaml liegt)
component_path = Path(__file__).parent / "components" / "ai_pipeline"

# Pfad zu dem 'defs' Ordner, in dem die defs.yaml liegt
defs_path = Path(__file__).parent / "defs_dev"

# Definitionen laden
defs = build_component_defs(defs_path)   # sonst war_defs



