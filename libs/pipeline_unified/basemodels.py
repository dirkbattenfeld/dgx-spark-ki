# /libs/pipeline/basemodels.py

# =====================================================================
# Basic Pipeline Environment
# Enriched by special environment for each pipeline 
# =====================================================================
import asyncio
from typing import ClassVar, Optional, Set
from pydantic import BaseModel
from libs.ki_dgxsdk.ki_sdk import DGX_Client

class BasePipelineEnv:
    """
    GENERISCH: Kontrolliert plattformunabhängig die Concurrency 
    und hält die rohe SDK-Verbindung.
    """
    def __init__(self, use_dispatcher: bool, config_path: Optional[str], max_concurrent_docs: int):
        # Basis-SDK initialisieren
        self.sdk = DGX_Client(
            use_dispatcher=use_dispatcher,
            config_path=config_path
        )
        # Globaler Semaphore für Dokumenten-Parallelität
        self.doc_semaphore = asyncio.Semaphore(max_concurrent_docs)
        

# =====================================================================
# BaseComponentResult should be imported from ki_pipeline
# Only needed for compatibility 
# =====================================================================

class BaseComponentResult(BaseModel):
    # Die Whitelist der erlaubten privaten Attribute
    ALLOWED_PRIVATE_ATTRS: ClassVar[Set[str]] = {
        "_pipeline_outputs", # Liste der Attribute, die in allen Projektoren in die PipelineResults aufgenommen werden
        "_drop_outputs"      # Liste der Attribute, die nicht in die PipelineResults gelangen
    }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        for attr_name in cls.__dict__:
            # Wir ignorieren Dunder-Attribute wie __module__ oder __doc__
            if attr_name.startswith("__") and attr_name.endswith("__"):
                continue
                
            # Wir prüfen nur echte private/geschützte Attribute (starten mit _)
            if attr_name.startswith("_"):
                if attr_name not in cls.ALLOWED_PRIVATE_ATTRS:
                    raise AttributeError(
                        f"Unzulässiges privates Attribut '{attr_name}' in Klasse '{cls.__name__}'. "
                        f"Erlaubt sind nur: {cls.ALLOWED_PRIVATE_ATTRS}"
                    )