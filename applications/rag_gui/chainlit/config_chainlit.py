import os
import importlib
from rag_gui.core.config_core import core_orchestrator

# Holt gezielt die Chainlit-Variante aus der zentralen .env
PRES_MODULE = os.getenv("CHAINLIT_PRESENTER_MODULE", "rag_gui.chainlit.presenter")
PRES_CLASS = os.getenv("CHAINLIT_PRESENTER_CLASS", "ChainlitPresenter")

pres_mod = importlib.import_module(PRES_MODULE)
presenter_class = getattr(pres_mod, PRES_CLASS)

active_presenter = presenter_class(orchestrator=core_orchestrator)