import httpx
from typing import Any, Dict

class PipelineClient:
    def __init__(self, config: Dict[str, Any], host: str = "gx10"):
        # Extrahiere Infos aus der Generator-Config
        gen_config = config.get("generator_config", {})
        self.port = gen_config.get("port", 8010)
        self.base_url = f"http://{host}:{self.port}"
        
        # Punkt 4: Dynamische Erkennung der erwarteten Parameter
        self.expected_keys = [
            item["payload_key"] for item in gen_config.get("mapping", [])
        ]

    def stop_pipeline(self):
        """Sendet den Shutdown-Request."""
        with httpx.Client() as client:
            try:
                response = client.post(f"{self.base_url}/shutdown")
                return response.json()
            except httpx.ConnectError:
                return {"status": "already offline"}

    def trigger_rag(self, **kwargs):
        """
        Sendet einen Request basierend auf den erlaubten Keys in der Config.
                """
        # Nur Keys senden, die auch im Mapping definiert sind
        payload = {k: v for k, v in kwargs.items() if k in self.expected_keys}
        
        # Validierung (optional)
        missing = set(self.expected_keys) - set(payload.keys())
        if missing:
            print(f"Warnung: Fehlende Keys im Request: {missing}")

        with httpx.Client() as client:
            response = client.post(f"{self.base_url}/trigger", json=payload)
            return response.json()


config={
  "generator_config": {
    "port": 8010,
    "mapping": [
      {
        "payload_key": "prompt",
        "target": ["question_selector", "user_query"]
      },
      {
        "payload_key": "collection",
        "target": ["search_qdrant", "collection_name"]
      },
      {
        "payload_key": "collection",
        "target": ["fetch_parents", "collection_name"],
        "suffix": "_parents"
      }
    ]
  }
}


client = PipelineClient(config)
client.trigger_rag(prompt="Wer sind die Autoren des papers im Context?", collection="morals_markets")