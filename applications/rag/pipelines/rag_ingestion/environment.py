# /applications/rag/pipelines/rag_ingestion/environment.py

import logging
from typing import List, Optional
from libs.storage.client import StorageClient
from libs.pipeline.basemodels import BasePipelineEnv
from applications.rag.pipelines.rag_ingestion.config import IngestionEnvConfig

logger = logging.getLogger(__name__)
class PdfIngestionEnv(BasePipelineEnv):
    """
    Kapselt Ressourcen und SDK-Clients für den RAG Ingestion Flow.
    Errechnet keine eigenen Defaults mehr, sondern liest diese aus der Config.
    """
    def __init__(self, config: IngestionEnvConfig):
        super().__init__(
            use_dispatcher=config.use_dispatcher,
            config_path=config.config_path,
            max_concurrent_docs=config.max_concurrent_documents
        )
        self.config = config
        
        # S3 Storage Client
        self.storage = StorageClient()
        
        # Registrieren aller benötigten SDK-Clients für dynamische Injection in Steps
        self.register_client("docling_client", self.sdk.get_client("docling"))
        self.register_client("vllm_client", self.sdk.get_client("vllm"))
        self.register_client("infinity_client", self.sdk.get_client("infinity"))
        self.register_client("qdrant_client", self.sdk.get_client("qdrant"))
        self.register_client("qdrant_service", self.sdk.get_client("qdrant")) # Aliase falls nötig
        self.register_client("storage_client", self.storage)

    def scan_source_files(self, override_bucket: Optional[str] = None) -> List[str]:
        """
        Sammelt die Quell-Pfade exklusiv für diesen Flow basierend auf der Config
        oder über einen override in der Signatur.
        """
        target_bucket = override_bucket or self.config.s3_bucket
        logger.info("📂 [PdfEnv] Scanne S3 Bucket '%s' nach '%s'...", target_bucket, self.config.s3_glob_pattern)
        return self.storage.list_files(
            bucket=target_bucket, 
            glob_pattern=self.config.s3_glob_pattern
        )
