import os
import httpx
import yaml
from pathlib import Path
import logging
import copy
from typing import Any, Dict, Optional, Type
from abc import ABC, abstractmethod
from pydantic import BaseModel

logger = logging.getLogger("DGX_Client")

# ==========================================
# DISPATCHER PROTOKOLL 
# ==========================================

class DispatcherJob(BaseModel):
    service_id: str
    endpoint: str
    queue_id: str
    batching: bool
    max_batch_size: int
    payload: Dict[str, Any]

# ==========================================
# TRANSPORT-SCHICHT (Reines I/O)
# ==========================================

class BaseTransport(ABC):
    """Abstrakte Basisklasse, die die Schnittstelle für alle Transporte definiert."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    @abstractmethod
    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Führt einen synchronen POST-Request aus."""
        pass

    @abstractmethod
    async def post_async(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Führt einen asynchronen POST-Request aus."""
        pass


class HTTPXTransport(BaseTransport):
    """Implementiert das Transport-Interface basierend auf HTTPX für Sync & Async."""
    
    def __init__(self, base_url: str):
        super().__init__(base_url)
        self._sync_client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

    @property
    def sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(timeout=None)
        return self._sync_client

    @property
    def async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=None)
        return self._async_client

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        clean_path = f"/{path.lstrip('/')}"
        response = self.sync_client.post(f"{self.base_url}{clean_path}", json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Transport Error [{response.status_code}]: {response.text}")
        return response.json()

    async def post_async(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        clean_path = f"/{path.lstrip('/')}"
        response = await self.async_client.post(f"{self.base_url}{clean_path}", json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Transport Error [{response.status_code}]: {response.text}")
        return response.json()
    

class DispatcherTransport(HTTPXTransport):
    """
    Kapselt die Dispatcher-Logik vollautomatisch. Die logischen Clients 
    (Mapping, VLLM) merken nicht, dass sie mit dem Dispatcher sprechen.
    """
    
    def __init__(self, dispatcher_url: str, service_id: str, service_cfg: Dict[str, Any]):
        super().__init__(dispatcher_url)
        self.service_id = service_id
        self.service_cfg = service_cfg

    def _build_job(self, path: str, payload: Dict[str, Any]) -> dict:
        # Der Job wird anhand der geladenen microservices.yaml gebaut
        job = DispatcherJob(
            service_id=self.service_id,
            endpoint=path.lstrip("/"), # z.B. "chat" oder "extract"
            queue_id=self.service_cfg.get("queue_id", "standard"),
            batching=self.service_cfg.get("batching", False),
            max_batch_size=self.service_cfg.get("max_batch_size", 1),
            payload=payload
        )
        return job.model_dump()

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return super().post("/submit", self._build_job(path, payload))

    async def post_async(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await super().post_async("/submit", self._build_job(path, payload))
    

# ============================================
# LOGISCHE CLIENTS 
# ============================================

class MicroServiceClient:
    """Nutzt das BaseTransport Interface."""
    def __init__(self, service_id: str, transport: BaseTransport, config: Dict[str, Any]):
        self.service_id = service_id
        self.transport = transport  # Typ ist jetzt garantiert!
        self.config = config

    def call(self, endpoint_name: str, payload: Dict[str, Any]) -> dict:
        endpoints_cfg = self.config.get("endpoints", {})
        endpoint_path = endpoints_cfg.get(endpoint_name, {}).get("path", f"/{endpoint_name}")
        
        # IDE weiß genau: .post() existiert auf BaseTransport
        return self.transport.post(endpoint_path, payload)

    async def call_async(self, endpoint_name: str, payload: Dict[str, Any]) -> dict:
        endpoints_cfg = self.config.get("endpoints", {})
        endpoint_path = endpoints_cfg.get(endpoint_name, {}).get("path", f"/{endpoint_name}")
        
        # IDE weiß genau: .post_async() existiert und muss geawaited werden
        return await self.transport.post_async(endpoint_path, payload)

class MappingClient:
    """
        Erweitert den BaseClient um die Fähigkeit, flache Eingaben und den Output dynamisch
        nach den Regeln der microservices.yaml zu mappen.
    """
    def __init__(self, service_id: str, transport: BaseTransport, config_data: Dict[str, Any]):
        self.service_name = service_id
        self.transport = transport
        self.service_cfg = config_data
    
         
    def _prepare_request(self, endpoint_name: str, kwargs: Dict[str, Any]):
        """Orchestriert das Inbound-Mapping."""
        endpoint_cfg = self.service_cfg.get("endpoints", {}).get(endpoint_name, {})
        if not endpoint_cfg:
            raise ValueError(f"Endpunkt '{endpoint_name}' ist nicht konfiguriert.")
        
        raw_path = endpoint_cfg.get("path", f"/{endpoint_name}")

        try:
            path = raw_path.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Für den Pfad {raw_path} fehlt das Argument: {e}")

        # =====================================================================
        # HIER STARTET DIE NEUE WEICHE
        # =====================================================================
        if "output_mapping" in endpoint_cfg:
            # Nutzt das flexible Inbound-Mapping für moderne Pipelines
            payload = self._build_standard_payload(endpoint_cfg, kwargs)
            return path, payload, endpoint_cfg
        # =====================================================================
        
        
    # --- EINHEITLICHER SYNCHRONER EINSTIEG ---
    def call(self, endpoint_name: str, **kwargs: Any) -> Dict[str, Any]:
        """Bereitet Daten auf, sendet sie synchron und mappt das Ergebnis."""
        path, payload, endpoint_cfg = self._prepare_request(endpoint_name, kwargs)
        
        try:
            raw_response = self.transport.post(path, payload)
        except Exception as e:
            logger.error(f"Fehler beim Aufruf von {endpoint_name}: {e}")
            return {"status": "error", "message": str(e)}
        
        if raw_response.get("status") == "error": 
            return raw_response
        return self._transform_response(endpoint_cfg, raw_response)


    # --- EINHEITLICHER ASYNCHRONER EINSTIEG ---
    async def call_async(self, endpoint_name: str, **kwargs: Any) -> Dict[str, Any]:
        """Bereitet Daten auf, sendet sie asynchron und mappt das Ergebnis."""
        path, payload, endpoint_cfg = self._prepare_request(endpoint_name, kwargs)
        
        try:
            raw_response = await self.transport.post_async(path, payload)
        except Exception as e:
            logger.error(f"Fehler beim Aufruf von {endpoint_name}: {e}")
            return {"status": "error", "message": str(e)}
        
        if raw_response.get("status") == "error": 
            return raw_response
        return self._transform_response(endpoint_cfg, raw_response)

    
    def _build_standard_payload(self, endpoint_cfg: Dict[str, Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Baut Payload durch Mergen der Defaults mit den gemappten User-Inputs."""
        
        # 1. Start: Komplette Struktur aus der YAML übernehmen (kein Flachklopfen!)
        payload = copy.deepcopy(endpoint_cfg.get("defaults", {}))
        
        # 2. Mapping-Regeln laden
        input_mapping = endpoint_cfg.get("input_mapping", {})
        
        # 3. User-Inputs gemäss Mapping an die richtige Stelle injizieren
        for key, value in kwargs.items():
            if key in input_mapping:
                path = input_mapping[key]
                # Inject-Logik: Wandert in den Baum und überschreibt/erstellt
                self._inject_at_path(payload, path, value)
            else:
                # Fallback: Root-Ebene (falls nicht gemappt)
                payload[key] = value
                
        return payload
    

    def _inject_at_path(self, data: Dict[str, Any], path: str, value: Any):
        """
        Injiziert einen Wert in einen Pfad. Unterscheidet sauber zwischen
        Dict-Pfade (z. B. 'payload.prompt_query') und direkter Payload-Ersetzung.
        """
        if not path:
            return

        parts = path.split(".")
        current = data
        
        for part in parts[:-1]:
            current = current.setdefault(part, {})
            
        target_key = parts[-1]

        # Spezialfall: Wenn der Ziel-Pfad genau 'payload' ist und ein Array/Liste übergeben wird,
        # soll die Liste direkt als Payload injiziert werden (wichtig für Ingestion Payloads!)
        if target_key == "payload" and isinstance(value, list):
            current[target_key] = value
        else:
            current[target_key] = value

    def _inject_at_path_old(self, data: Dict, path: str, value: Any):
        """Injiziert einen Wert in einen Pfad, ohne bestehende Strukturen zu zerstören."""
        parts = path.split(".")
        current = data
        for part in parts[:-1]:
            # Wenn der Pfad nicht existiert, wird ein dict erstellt
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    
    
    def _get_deep_value(self, data: Dict[str, Any], path: str) -> Any:
        """Löst Punktnotationen wie 'steps.GenerateLLM.extras.model' rekursiv auf."""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current
        
    def _transform_response(self, endpoint_cfg: Dict[str, Any], raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """Übersetzt das Server-JSON einheitlich via output_mapping (Punktnotation)."""
        output_map = endpoint_cfg.get("output_mapping")
        
        # Falls gar kein Mapping deklariert ist (z.B. leere Antworten / Status-Pings)
        if not output_map:
            return raw_response
            
        transformed = {}
        for sdk_key, api_path in output_map.items():
            if isinstance(api_path, dict):
                # Für verschachtelte Strukturen (z.B. generation_info)
                sub_dict = {}
                for sub_key, sub_path in api_path.items():
                    sub_dict[sub_key] = self._get_deep_value(raw_response, sub_path)
                transformed[sdk_key] = sub_dict
            else:
                # Für flache Keys ODER tiefe Punktnotation (sucht rekursiv)
                transformed[sdk_key] = self._get_deep_value(raw_response, api_path)
                
        return transformed
    

# =============================================================
# Spezialisierte Clients für mehr Komfort 
# ============================================================= 
class VLLMClient(MicroServiceClient):
    """Spezialisierter Client (Regel 3: Höherer Komfort für komplexe APIs)."""
    
    def _build_chat_payload(self, prompt: str, system_prompt: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "model": self.config.get("model_name", "auto"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }
        payload.update(kwargs)
        return payload
    
    def _transform_response(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transformiert das tief verschachtelte vLLM-JSON in ein flaches Komfort-Format."""
        # Fehler abfangen, falls die API gestreikt hat
        if "choices" not in raw or not raw["choices"]:
            return {"text": "", "error": "Ungültige Antwort von vLLM", "raw_result": raw}

        choices = raw["choices"]
        usage = raw.get("usage", {})

        # Das flache Komfort-Dict aufbauen
        return {
            "text": choices[0].get("message", {}).get("content", ""),
            "model": raw.get("model", ""),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            # Das komplette Original-Ergebnis für Power-User mitsenden
            "raw_result": raw 
        }
    
    def chat(self, prompt: str, system_prompt: str = "You are a helpful assistant.", **kwargs) -> dict:
        payload = self._build_chat_payload(prompt, system_prompt, kwargs)
        # 1. Rohe Antwort holen
        raw_response = super().call("chat", payload)
        # 2. Transformieren und zurückgeben
        return self._transform_response(raw_response)

    async def chat_async(self, prompt: str, system_prompt: str = "You are a helpful assistant.", **kwargs) -> dict:
        payload = self._build_chat_payload(prompt, system_prompt, kwargs)
        # 1. Rohe Antwort asynchron holen
        raw_response = await super().call_async("chat", payload)
        # 2. Transformieren und zurückgeben
        return self._transform_response(raw_response)

class InfinityClient(MicroServiceClient):
    """
    Spezialisierter Client für den Infinity-Server.
    Unterstützt performante Embeddings und Reranking (Sync & Async).
    """

    # --- EMBEDDINGS METHODS ---
    def embeddings(self, texts: list[str], model: Optional[str] = None) -> list[list[float]]:
        """Erzeugt dichte Vektoren für eine Liste von Texten."""
        # Hole das Standardmodell aus der YAML, falls keines übergeben wurde
        default_model = self.config.get("endpoints", {}).get("embeddings", {}).get("defaults", {}).get("model", "BAAI/bge-m3")
        
        payload = {
            "model": model or default_model,
            "input": texts
        }
        
        # Nutzt den korrekten Pfad aus der YAML oder Fallback
        path = self.config.get("endpoints", {}).get("embeddings", {}).get("path", "/embeddings")
        raw_response = super().call(path.lstrip("/"), payload)
        
        if "data" not in raw_response:
            raise RuntimeError(f"Infinity Embeddings Error: {raw_response.get('message', 'Unknown error')}")
            
        return [item["embedding"] for item in raw_response["data"]]

    async def embeddings_async(self, texts: list[str], model: Optional[str] = None) -> list[list[float]]:
        """Asynchrone Erzeugung von Embeddings."""
        default_model = self.config.get("endpoints", {}).get("embeddings", {}).get("defaults", {}).get("model", "BAAI/bge-m3")
        payload = {"model": model or default_model, "input": texts}
        path = self.config.get("endpoints", {}).get("embeddings", {}).get("path", "/embeddings")
        
        raw_response = await super().call_async(path.lstrip("/"), payload)
        if "data" not in raw_response:
            raise RuntimeError(f"Infinity Embeddings Error: {raw_response.get('message', 'Unknown error')}")
            
        return [item["embedding"] for item in raw_response["data"]]


    # --- RERANK METHODS ---
    def rerank(self, query: str, documents: list[str], top_n: Optional[int] = None, model: Optional[str] = None) -> list[dict]:
        """
        Sortiert Dokumente basierend auf der Relevanz zur Query neu.
        Gibt eine sortierte Liste von Dicts zurück: [{'index': int, 'relevance_score': float, 'document': str}]
        """
        endpoint_cfg = self.config.get("endpoints", {}).get("rerank", {})
        default_model = endpoint_cfg.get("defaults", {}).get("model", "BAAI/bge-reranker-v2-m3")
        default_top_n = endpoint_cfg.get("defaults", {}).get("top_n", 5)

        payload = {
            "model": model or default_model,
            "query": query,
            "documents": documents,
            "top_n": top_n or default_top_n
        }

        path = endpoint_cfg.get("path", "/rerank")
        raw_response = super().call(path.lstrip("/"), payload)

        if "results" not in raw_response:
            raise RuntimeError(f"Infinity Rerank Error: {raw_response.get('message', 'Unknown error')}")

        # Komfort-Feature: Wir fügen den originalen Text des Dokuments direkt wieder hinzu,
        # damit die Pipeline nicht mühsam über den Index zurückmappen muss.
        processed_results = []
        for item in raw_response["results"]:
            idx = item["index"]
            processed_results.append({
                "index": idx,
                "relevance_score": item["relevance_score"],
                "document": documents[idx]  # Direktes Text-Mapping!
            })

        return processed_results

    async def rerank_async(self, query: str, documents: list[str], top_n: Optional[int] = None, model: Optional[str] = None) -> list[dict]:
        """Asynchrones Reranking."""
        endpoint_cfg = self.config.get("endpoints", {}).get("rerank", {})
        default_model = endpoint_cfg.get("defaults", {}).get("model", "BAAI/bge-reranker-v2-m3")
        default_top_n = endpoint_cfg.get("defaults", {}).get("top_n", 5)

        payload = {
            "model": model or default_model,
            "query": query,
            "documents": documents,
            "top_n": top_n or default_top_n
        }

        path = endpoint_cfg.get("path", "/rerank")
        raw_response = await super().call_async(path.lstrip("/"), payload)

        if "results" not in raw_response:
            raise RuntimeError(f"Infinity Rerank Error: {raw_response.get('message', 'Unknown error')}")

        return [{
            "index": item["index"],
            "relevance_score": item["relevance_score"],
            "document": documents[item["index"]]
        } for item in raw_response["results"]]

class QdrantService(MicroServiceClient):
    """
    Spezialisierter Service für Qdrant.
    Übernimmt die vollständige Konfiguration aus der microservices.yaml.
    Liefert den offiziellen, voll typisierten AsyncQdrantClient via Lazy-Import.
    """
    def __init__(self, service_id: str, transport: BaseTransport, config: Dict[str, Any]):
        super().__init__(service_id, transport, config)
        # Automatische Konfiguration aus deiner YAML extrahieren
        self.host = self.config.get("host", "localhost")
        self.port = self.config.get("port", 6333)
        self.url = f"http://{self.host}:{self.port}"
        
        self._client = None

    @property
    def client(self) -> Any:
        """
        Liefert den fertig konfigurierten, asynchronen Original-Client von Qdrant.
        Der Import passiert erst beim Aufruf der Property (Schutz für das Monorepo!).
        """
        if self._client is None:
            try:
                from qdrant_client import AsyncQdrantClient
            except ImportError as e:
                raise ImportError(
                    "[DGX SDK FEHLER]: Das Paket 'qdrant-client' fehlt in diesem Environment/Container. "
                    "Bitte installiere es via 'pip install qdrant-client'."
                ) from e
            
            # Instanziierung mit den aus der YAML ausgelesenen Daten
            self._client = AsyncQdrantClient(url=self.url, timeout=None)
        return self._client

# ==========================================
# DAS SDK mit Client Fabric
# ==========================================
class DGX_Client:

    def __init__(
        self,
        config_path: Optional[str] = None,
        config_data: Optional[Dict[str, Any]] = None,
        use_dispatcher: bool = False,
        dispatcher_url: Optional[str] = None,
    ):
        self.use_dispatcher = use_dispatcher
        self.dispatcher_url = dispatcher_url or os.environ.get("DISPATCHER_URL", "http://100.67.8.64:8000")
        self.config = {"services": {}}

        # Basis-Registry für komfortable Spezial-Clients
        self.registry: Dict[str, Type[MicroServiceClient]] = {
            "vllm": VLLMClient,
            "infinity": InfinityClient,
            "qdrant": QdrantService
        }

        # Strategie 1: Direktes Dict (höchste Priorität, perfekt für Tests)
        if config_data is not None:
            self.config = config_data
            self.config_path = None
            return

        # Strategie 2: Pfad über die intelligente Kaskade auflösen
        # oder microservices.yaml über Dispatcher holen
        if self.use_dispatcher:
            self._load_remote_config()
        else:
            self.config_path = self._resolve_config_path(config_path)
            with open(self.config_path, "r") as f:
                self.config = yaml.safe_load(f) or {"services": {}}


    def _load_remote_config(self):
        """[NEU] Holt die YAML direkt vom Dispatcher."""
        try:
            logger.info(f"🔄 Beziehe Konfiguration von {self.dispatcher_url}/routes ...")
            # Synchroner Request, da __init__ synchron ist
            response = httpx.get(f"{self.dispatcher_url}/routes", timeout=5.0)
            response.raise_for_status()
            self.config = response.json()
            logger.info("✅ Remote-Konfiguration erfolgreich geladen.")
        except Exception as e:
            logger.error(f"❌ Fehler beim Laden der Remote-Config: {e}")
            raise RuntimeError("SDK kann ohne Dispatcher-Config nicht arbeiten.") from e
        
    
    def _resolve_config_path(self, explicit_path: Optional[str] = None) -> str:
        """Sucht die microservices.yaml nach einer festen Prioritäten-Kaskade."""

        # Fall 4: Explizit per Code übergeben (Höchste Priorität)
        if explicit_path:
            if os.path.exists(explicit_path):
                return explicit_path
            raise FileNotFoundError(
                f"[DGX SDK FEHLER]: Explizit übergebene Konfiguration unter '{explicit_path}' nicht gefunden."
            )

        # Fall 3: Über Umgebungsvariable gesetzt (Für große Projekte/Docker/pydantic_settings)
        env_path = os.environ.get("MICROSERVICE_CONFIG_PATH")
        if env_path and os.path.exists(env_path):
            return env_path

        # Fall 2: Im Verzeichnis des startenden Skripts/Notebooks (deine ursprüngliche Logik)
        try:
            script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            script_path = os.path.join(script_dir, "microservices.yaml")
            if os.path.exists(script_path):
                return script_path
        except Exception:
            pass

        # Fall 1a: Aktuelles Arbeitsverzeichnis des Terminals (CWD)
        cwd_path = os.path.join(os.getcwd(), "microservices.yaml")
        if os.path.exists(cwd_path):
            return cwd_path

        # Fall 1b: Globaler Standard-Ort im Home-Verzeichnis (~/configs/microservices.yaml)
        home_fallback = os.path.join(
            Path.home(), "configs", "microservices.yaml"
        )
        if os.path.exists(home_fallback):
            return home_fallback

        # Wenn absolut kein Pfad matches liefert:
        raise FileNotFoundError(
            "[DGX SDK FEHLER]: Keine 'microservices.yaml' gefunden! Bitte übergeben Sie den Pfad "
            "explizit, setzen Sie MICROSERVICE_CONFIG_PATH oder legen Sie die Datei in Ihr Skriptverzeichnis."
        )
   
    def register_client_class(self, service_type: str, client_class: Type[MicroServiceClient]):
        """Erlaubt das dynamische Erweitern des SDKs um neue Client-Typen."""
        self.registry[service_type] = client_class

    def get_client(self, service_id: str) -> Any:
        """Erstellt den passenden Client mit dem korrekten Transport-Injektions-Verfahren."""
        services_cfg = self.config.get("services", {})
        s_cfg = services_cfg.get(service_id, {})
        
        # 1. TRANSPORT-SCHICHT INJIZIEREN
        if self.use_dispatcher:
            transport = DispatcherTransport(self.dispatcher_url, service_id=service_id, service_cfg=s_cfg)
        else:
            host = s_cfg.get("host", "localhost")
            port = s_cfg.get("port", 80)
            transport = HTTPXTransport(base_url=f"http://{host}:{port}")

        # 2. CLIENT-KLASSE AUTOMATISCH BESTIMMEN (Factory Logic)
        if service_id in self.registry: 
            client_class = self.registry[service_id]
        elif "endpoints" in s_cfg:
            client_class = MappingClient
        else:
            client_class = MicroServiceClient
            
        # Aufruf erfolgt positionell, da beide Client-Typen 3 Argumente erwarten
        return client_class(service_id, transport, s_cfg)
