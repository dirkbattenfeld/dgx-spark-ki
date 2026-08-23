# llm/llama.py
#####################################
# Local LLaMA LLM Klasse
#####################################

import requests
from typing import Any, List, Optional, Mapping
from pydantic import BaseModel

# LLM Config
class LlmConfig(BaseModel):
    device: str = "cpu"
    n_predict: int = 4096
    temperature: float = 1.0
    top_p: float = 1.0
    top_k: int = 1
    repeat_penalty: float = 1.0
    streaming: bool = False

# Minimal-Basisklasse LLM, nur damit LangChain die Instanz akzeptiert
class LLM:
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        raise NotImplementedError()

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {}

    @property
    def _llm_type(self) -> str:
        return "custom_llm"

class LocalLlamaLLM(LLM):
    """Implementation eines lokalen LLaMA LLM.

    Verwendet intern:
    - LLM: Basisklasse für LLMs
    - LlmConfig: Konfigurationsobjekt
    - clean_antwort_llm: Hilfsfunktion zum Säubern von Antworten
    """

    endpoint: Optional[str] = None

    class Config:
        extra = "allow" #erlaubt in Pydantic dynamische Attribute

    def __init__(self, device: str = "cpu", config: LlmConfig = None):
        super().__init__()
        self.config = config or LlmConfig() # Default falls Config = None
        # Device-basiertes Endpoint-Mapping
        endpoints = {
            "gpu": "http://172.25.0.10:5001/completion",
            "cpu": "http://172.25.0.11:5000/completion",
        }
    
        endpoints_old = {
            "gpu": "http://llama-gpu:5001/completion",
            "cpu": "http://llama-cpu:5000/completion",
        }
        self.endpoint = endpoints.get(device, endpoints["cpu"])
        
    def _call(self, prompt: str, llm_override: Optional[LlmConfig] = None, stop: Optional[List[str]] = None) -> str:
        cfg = llm_override or self.config
        
        response = requests.post(
            self.endpoint,
            json={
                "prompt": prompt,
                "n_predict": cfg.n_predict,
                "temperature": cfg.temperature,
                "top_p": cfg.top_p,
                "top_k": cfg.top_k,
                "repeat_penalty": cfg.repeat_penalty,
                "streaming": cfg.streaming
            }
        )
        response.raise_for_status()
        data = response.json()
        return data.get("content", "")

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"endpoint": self.endpoint}

    @property
    def _llm_type(self) -> str:
        return "local_llama"

# Hilfsfunktion zum Säubern der Antwort des LLM
def clean_antwort_llm (antwort):
    clean_result = antwort.replace("Answer:", "").strip()
    return clean_result
