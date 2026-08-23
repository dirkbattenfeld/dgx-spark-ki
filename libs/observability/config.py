# libs/observability/config.py

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

SinkType = Literal["console", "otlp", "jsonl"]

class ChannelConfig(BaseModel):
    enabled_sinks: List[SinkType] = Field(default_factory=lambda: ["console"])
    log_level: str = Field(default="INFO", description="Kanal-spezifisches Mindest-Level")

class ObservabilityConfig(BaseModel):
    service_name: str = Field(default="streampipe-service")
    global_log_level: str = Field(default="INFO")
    
    # Globaler Schalter für OTLP-Exporte
    otlp_enabled: bool = Field(default=False, description="Aktiviert/Deaktiviert den OTLP-Export zu Collector/HyperDX")
    
    # Mapping von Namespaces auf LogLevels (für System-Logging)
    namespace_levels: Dict[str, str] = Field(
        default_factory=lambda: {
            "libs.pipeline": "INFO",
            "applications.rag": "DEBUG",
            "libs.observability": "INFO",
            # Drittanbieter & Frameworks
            "uvicorn": "INFO",
            "uvicorn.error": "INFO",
            "uvicorn.access": "WARNING",  # Blendet normale Request-Access-Logs bei Bedarf aus
            "fastapi": "INFO",
            "httpx": "WARNING",
            "qdrant_client": "WARNING",
        }
    )
        
    # Kanal-Routing (Traces, Data, System)
    channels: Dict[str, ChannelConfig] = Field(
        default_factory=lambda: {
            "trace": ChannelConfig(enabled_sinks=["console", "otlp"], log_level="INFO"),
            "data": ChannelConfig(enabled_sinks=["jsonl"], log_level="INFO"),
            "system": ChannelConfig(enabled_sinks=["console"], log_level="INFO")
        }
    )
    
    otlp_endpoint: str = Field(default="http://100.67.8.64:4318")            #"http://localhost:4318")
    jsonl_filepath: str = Field(default="projects/streampipe_logs/pipeline_execution.log")




