from typing import Optional, List
from libs.storage.client import StorageClient
from libs.streampipe.basemodels import BasePipelineEnv
from libs.streampipe.observability import SimpleTraceConfig

class ExtractPipelineConfig:
    USE_DISPATCHER: bool = True
    CONFIG_PATH: Optional[str] = None
    MAX_CONCURRENT_DOCUMENTS: int = 4
    S3_BUCKET = "extract-01"
    S3_GLOB_PATTERN = "*.docling.chunks.json"
    
    TRACE_CONFIG: SimpleTraceConfig = SimpleTraceConfig(
        filepath="projects/streampipe_logs/extract.jsonl", 
        log_full_input = True,
        trace_to_terminal = False,
        trace_to_file = True,
        data_to_terminal = False,
        data_to_file = True
        )
    
class ExtractPipelineEnv(BasePipelineEnv):
    """
    SPEZIFISCH: Hält die Konfiguration und die über das SDK 
    aufgelösten Microservice-Clients für den Request-Flow.
    """
    def __init__(self, config: ExtractPipelineConfig): 
        BasePipelineEnv.__init__(
            self,
            use_dispatcher=config.USE_DISPATCHER,
            config_path=config.CONFIG_PATH,
            max_concurrent_docs=config.MAX_CONCURRENT_DOCUMENTS
        )
        
        # Konfiguration sichern
        self.config = config
        self.trace_config = config.TRACE_CONFIG
        
        # Ressourcen laden
        print("️[ExtractEnv] Lade Storage-Client über das Storage-SDK...")
        self.storage_client = StorageClient()       
        print("[ExtractEnv] Lade Microservice-Clients über das DGX-SDK...")
        self.vllm_client = self.sdk.get_client("vllm")
    
    def scan_source_files(self) -> List[str]:
        """Sammelt die Quell-PDF-Pfade exklusiv für diesen Flow."""
        print(f"📂 [PdfEnv] Scanne S3 Bucket '{self.config.S3_BUCKET}' nach '{self.config.S3_GLOB_PATTERN}'...")
        return self.storage_client.list_files(bucket=self.config.S3_BUCKET, glob_pattern=self.config.S3_GLOB_PATTERN)

def run_preparation() -> ExtractPipelineEnv:
    config = ExtractPipelineConfig()
    env = ExtractPipelineEnv(config=config)
    
    # 🚀 Hier aktivieren wir die Observability einmalig für den gesamten Prozess!
    from libs.streampipe.observability import configure_observability
    configure_observability(config.TRACE_CONFIG)
    
    return env