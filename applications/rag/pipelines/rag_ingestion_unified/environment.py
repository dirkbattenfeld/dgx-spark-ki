# /applications/rag/pipelines/rag_ingestion/environment.py

# =====================================================================
# GLOBAL CONFIGURATION
# =====================================================================
from typing import List, Optional
from libs.storage.client import StorageClient
from libs.streampipe.basemodels import BasePipelineEnv
from libs.streampipe.observability import SimpleTraceConfig

class IngestionConfig:
    USE_DISPATCHER: bool = True
    CONFIG_PATH: Optional[str] = None
    MAX_CONCURRENT_DOCUMENTS: int = 5
    S3_BUCKET = "office-test"                 # <---
    S3_GLOB_PATTERN = "*.pptx"                # <---
    DEFAULT_VLLM_SYSTEM_PROMPT = "Du bist ein präziser Dokumentanalyst."
    
    TRACE_CONFIG: SimpleTraceConfig = SimpleTraceConfig(
        filepath="projects/streampipe_logs/rag_ingestion.jsonl", 
        log_full_input = True,
        trace_to_terminal = False,
        trace_to_file = True,
        data_to_terminal = False,
        data_to_file = True
        )
   
class PdfIngestionEnv(BasePipelineEnv):
    """
    SPEZIFISCH: Kennt die konkreten Microservices und S3-Strukturen 
    für den PDF-Ingestion-Flow.
    """
    def __init__(self, config: IngestionConfig):
        BasePipelineEnv.__init__(
            self,
            use_dispatcher=config.USE_DISPATCHER,
            config_path=config.CONFIG_PATH,
            max_concurrent_docs=config.MAX_CONCURRENT_DOCUMENTS
        )
        self.config = config
        self.trace_config = config.TRACE_CONFIG
        
        # 2. Pipeline-spezifische Ressourcen initialisieren
        print("🛰️ [IngestionEnv] Verbinde mit S3-Speicher und lade RAG-Clients...")
        self.storage = StorageClient()
        
        # Spezifische Client-Zuweisungen
        self.docling_client = self.sdk.get_client("docling")
        self.vllm_client = self.sdk.get_client("vllm")
        self.infinity_client = self.sdk.get_client("infinity")
        self.qdrant_client = self.sdk.get_client("qdrant")
            
    def scan_source_files(self) -> List[str]:
        """Sammelt die Quell-PDF-Pfade exklusiv für diesen Flow."""
        print(f"📂 [PdfEnv] Scanne S3 Bucket '{self.config.S3_BUCKET}' nach '{self.config.S3_GLOB_PATTERN}'...")
        return self.storage.list_files(bucket=self.config.S3_BUCKET, glob_pattern=self.config.S3_GLOB_PATTERN)


def run_preparation() -> PdfIngestionEnv:
    """Initialisiert die spezifische RAG-Pipeline-Umgebung."""
    config = IngestionConfig()
    env = PdfIngestionEnv(config=config)
    
    # 🚀 Hier aktivieren wir die Observability einmalig für den gesamten Prozess!
    from libs.streampipe.observability import configure_observability
    configure_observability(config.TRACE_CONFIG)
    
    return env

