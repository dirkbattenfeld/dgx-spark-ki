import logging
from typing import Any

from ki_dgxsdk.ki_sdk import DGX_Client
from storage.client import StorageClient

from pipelines.ingestion_engine.db.session import async_session_maker

# 1. Importiere das saubere DB-Setup aus deiner Domain-Schicht
from pipelines.ingestion_engine.db.session import engine as db_engine

logger = logging.getLogger(__name__)

class InfrastructureContext:
    """
    Zentraler Container, der die bestehenden DB-Komponenten mit 
    dem Storage-Client und den DGX-Clients für den Worker-Stack vereint.
    """
    def __init__(
        self,
        storage_client: StorageClient,
        dgx_client: Any,
    ):
        # Wir nutzen die hier direkt mitgebrachten, sauberen Module
        self.db_engine = db_engine
        self.async_session_maker = async_session_maker
        
        self.storage_client = storage_client
        self.dgx_client = dgx_client
        
        # Shortcuts
        self.qdrant_client = dgx_client.get_client("qdrant")
        self.vllm_client = dgx_client.get_client("vllm")
        self.infinity_client = dgx_client.get_client("infinity")
        self.docling_client = dgx_client.get_client("docling")

    @classmethod
    async def create(cls, settings) -> "InfrastructureContext":
        logger.info("⚙️ Initialisiere Infrastruktur-Container...")
        
        storage_client = StorageClient()
        dgx_client = DGX_Client(
            use_dispatcher=settings.USE_DISPATCHER,
            config_path=settings.MICROSERVICE_CONFIG_PATH
        )
        
        return cls(
            storage_client=storage_client,
            dgx_client=dgx_client
        )

    async def close(self):
        logger.info("🛑 Fahre Infrastruktur-Container herunter...")
        await self.db_engine.dispose()
        # Falls DGX-Client oder Storage Schließmethoden haben:
        # if hasattr(self.dgx_client, "close"): await self.dgx_client.close()
