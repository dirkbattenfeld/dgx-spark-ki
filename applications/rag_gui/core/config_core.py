# applications/rag_gui/config_core.py
import os
import importlib
from ki_dgxsdk.ki_sdk import DGX_Client

# 1. Infrastruktur / SDK initialisieren
dgx_client = DGX_Client(use_dispatcher=True)

# 2. Dynamische Konfiguration aus den Umgebungsvariablen laden
# Für SQLite nutzen wir nun standardmäßig dein neues Modul
DB_MODULE = os.getenv("APP_DB_MODULE", "rag_gui.core.sqlite_repository")
DB_CLASS = os.getenv("APP_DB_CLASS", "SQLiteRepository")
ORCH_MODULE = os.getenv("APP_ORCHESTRATOR_MODULE", "rag_gui.core.orchestrator")
ORCH_CLASS = os.getenv("APP_ORCHESTRATOR_CLASS", "Orchestrator")

# Schalter für den Reset der Testdaten aus Umgebungsvariable lesen
RESET_DATABASE = os.getenv("APP_RESET_DB", "false").lower() == "true"
DB_FILE_PATH = os.getenv("APP_DB_PATH", "/tmp/dev_state.db")

# Dynamischer Import der Datenbank-Schicht (SQLite)
db_mod = importlib.import_module(DB_MODULE)
db_class = getattr(db_mod, DB_CLASS)

# Wir übergeben den clear_on_start Schalter an den Konstruktor
state_db = db_class(db_path=DB_FILE_PATH, clear_on_start=RESET_DATABASE)

# Import des EventBusPort
BUS_MODULE = os.getenv("APP_BUS_MODULE", "rag_gui.core.redis_bus")
BUS_CLASS = os.getenv("APP_BUS_CLASS", "RedisEventBus")

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Dynamischer Import der konkreten Infrastruktur-Klasse
bus_mod = importlib.import_module(BUS_MODULE)
bus_class = getattr(bus_mod, BUS_CLASS)

# Die Instanziierung übergibt die Parameter 
runtime_event_bus = bus_class(host=REDIS_HOST, port=REDIS_PORT)

# Dynamischer Import des Cores (Orchestrator) & Dependency Injection
orch_mod = importlib.import_module(ORCH_MODULE)
orchestrator_class = getattr(orch_mod, ORCH_CLASS)

# Der Kern ist nun bereit und greift auf die gesharedte Platte zu
core_orchestrator = orchestrator_class(
    state_repository=state_db,
    client=dgx_client,
    event_bus=runtime_event_bus
)
