# applications/rag/pipelines/rag_request.py

from libs.pipeline.basemodels import BasePipelineEnv
from applications.rag.pipelines.rag_request.config import RequestEnvConfig
    
class RagRequestEnv(BasePipelineEnv):
    """
    SPEZIFISCH: Hält die Konfiguration und die über das SDK 
    aufgelösten Microservice-Clients für den Request-Flow.
    """
    def __init__(self, config: RequestEnvConfig): 
        super().__init__(
            use_dispatcher=config.use_dispatcher,
            config_path=config.config_path,
            max_concurrent_docs=config.max_concurrency
        )
        
        # Konfiguration sichern
        self.config = config
        
        # Registrieren aller benötigten SDK-Clients für dynamische Injection in Steps
        self.register_client("vllm_client", self.sdk.get_client("vllm"))
        self.register_client("infinity_client", self.sdk.get_client("infinity"))
        self.register_client("qdrant_client", self.sdk.get_client("qdrant"))
        self.register_client("qdrant_service", self.sdk.get_client("qdrant")) # Aliase falls nötig
        
        # Ressourcen über get_client laden
        self.qdrant_client = self.sdk.get_client("qdrant")
        self.infinity_client = self.sdk.get_client("infinity")
        self.vllm_client = self.sdk.get_client("vllm")
