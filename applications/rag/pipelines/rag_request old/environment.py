from typing import Optional
from libs.streampipe.basemodels import BasePipelineEnv
from libs.streampipe.observability import SimpleTraceConfig

class RequestPipelineConfig:
    USE_DISPATCHER: bool = True
    CONFIG_PATH: Optional[str] = None
    MAX_CONCURRENT_DOCUMENTS: int = 10
    
    TRACE_CONFIG: SimpleTraceConfig = SimpleTraceConfig(
        filepath="projects/streampipe_logs/rag_request.jsonl", 
        log_full_input = True,
        trace_to_terminal = False,
        trace_to_file = True,
        data_to_terminal = False,
        data_to_file = True
        )
    
class RequestPipelineEnv(BasePipelineEnv):
    """
    SPEZIFISCH: Hält die Konfiguration und die über das SDK 
    aufgelösten Microservice-Clients für den Request-Flow.
    """
    def __init__(self, config: RequestPipelineConfig): 
        BasePipelineEnv.__init__(
            self,
            use_dispatcher=config.USE_DISPATCHER,
            config_path=config.CONFIG_PATH,
            max_concurrent_docs=config.MAX_CONCURRENT_DOCUMENTS
        )
        
        # Konfiguration sichern
        self.config = config
        self.trace_config = config.TRACE_CONFIG
        
        # Ressourcen über get_client laden
        print("🛰️ [RequestEnv] Lade RAG-Clients über das DGX-SDK...")
        self.qdrant_client = self.sdk.get_client("qdrant")
        self.infinity_client = self.sdk.get_client("infinity")
        self.vllm_client = self.sdk.get_client("vllm")


def run_preparation() -> RequestPipelineEnv:
    config = RequestPipelineConfig()
    env = RequestPipelineEnv(config=config)
    
    # 🚀 Hier aktivieren wir die Observability einmalig für den gesamten Prozess!
    from libs.streampipe.observability import configure_observability
    configure_observability(config.TRACE_CONFIG)
    
    return env