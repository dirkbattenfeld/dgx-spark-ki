#applications/rag_gui/nicegui/config_nicegui.py

import os
import importlib
from rag_gui.core.config_core import core_orchestrator

# Wir importieren den NiceGUIPresenter
PRES_MODULE = os.getenv("NICEGUI_PRESENTER_MODULE", "rag_gui.nicegui.presenter")
PRES_CLASS = os.getenv("NICEGUI_PRESENTER_CLASS", "NiceGUICockpitPresenter")

pres_mod = importlib.import_module(PRES_MODULE)
presenter_class = getattr(pres_mod, PRES_CLASS)

# Dependency Injection des Cores in den Streamlit-Presenter
active_presenter = presenter_class(orchestrator=core_orchestrator)