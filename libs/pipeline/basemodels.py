# /libs/pipeline/basemodels.py

import asyncio
from typing import Any, ClassVar, Dict, Optional, Set
from pydantic import BaseModel
from libs.ki_dgxsdk.ki_sdk import DGX_Client


class BasePipelineEnv:
    """
    GENERISCH: Kontrolliert plattformunabhängig die Concurrency,
    hält die SDK-Verbindung und stellt ein generisches Client-Mapping bereit.
    """
    def __init__(self, use_dispatcher: bool, config_path: Optional[str], max_concurrent_docs: int):
        self.sdk = DGX_Client(
            use_dispatcher=use_dispatcher,
            config_path=config_path
        )
        self.doc_semaphore = asyncio.Semaphore(max_concurrent_docs)
        self._clients: Dict[str, Any] = {}

    def register_client(self, name: str, client_instance: Any) -> None:
        """Registriert ein Service/Client-Objekt für die spätere Nutzung in den Steps."""
        self._clients[name] = client_instance

    def get_clients(self) -> Dict[str, Any]:
        """Liefert das vollständige Client-Dict für die dynamische Injection im Runner."""
        return self._clients


class BaseComponentResult(BaseModel):
    ALLOWED_PRIVATE_ATTRS: ClassVar[Set[str]] = {
        "_pipeline_outputs",
        "_drop_outputs"
    }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for attr_name in cls.__dict__:
            if attr_name.startswith("__") and attr_name.endswith("__"):
                continue
            if attr_name.startswith("_") and attr_name not in cls.ALLOWED_PRIVATE_ATTRS:
                raise AttributeError(
                    f"Unzulässiges privates Attribut '{attr_name}' in Klasse '{cls.__name__}'. "
                    f"Erlaubt sind nur: {cls.ALLOWED_PRIVATE_ATTRS}"
                )
