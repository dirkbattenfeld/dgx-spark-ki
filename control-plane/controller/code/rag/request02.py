import httpx
import json
import pandas as pd
from typing import Any, Dict
import plotly.express as px

class PipelineClient:
    def __init__(self, config: Dict[str, Any], host: str = "gx10"):
        # Extrahiere Infos aus der Generator-Config
        gen_config = config.get("generator_config", {})
        self.port = gen_config.get("port", 8010)
        self.base_url = f"http://{host}:{self.port}"
        
        # Dynamische Erkennung der erwarteten Parameter (mit set() für Einzigartigkeit)
        self.expected_keys = list(set(
            item["payload_key"] for item in gen_config.get("mapping", [])
        ))

    def stop_pipeline(self) -> Dict[str, Any]:
        """Sendet den Shutdown-Request."""
        with httpx.Client() as client:
            try:
                response = client.post(f"{self.base_url}/shutdown", timeout=10.0)
                return response.json()
            except (httpx.ConnectError, httpx.HTTPError) as e:
                return {"status": "error", "message": str(e)}

    def trigger_rag(self, **kwargs) -> Dict[str, Any]:
        """
        Filtert die Eingaben basierend auf der Config und gibt den API-Response zurück.
        """
        # Nur Keys senden, die auch im Mapping definiert sind
        payload = {k: v for k, v in kwargs.items() if k in self.expected_keys}
        
        # Validierung: Prüfen, ob alle erwarteten Keys vorhanden sind
        missing = set(self.expected_keys) - set(payload.keys())
        if missing:
            print(f"⚠️ Warnung: Folgende Keys fehlen im Request: {missing}")

        try:
            with httpx.Client() as client:
                # Sende den Request mit Timeout, um Hängenbleiben zu verhindern
                response = client.post(
                    f"{self.base_url}/trigger", 
                    json=payload, 
                    timeout=600.0
                )
                
                # Prüft auf HTTP-Fehler (4xx, 5xx) und wirft ggf. eine Exception
                response.raise_for_status()
                
                # Gibt das JSON-Resultat zurück
                return response.json()
                
        except httpx.ConnectError:
            return {"error": "Connection failed", "details": f"Server unter {self.base_url} nicht erreichbar."}
        except httpx.HTTPStatusError as e:
            return {"error": "HTTP Error", "status_code": e.response.status_code, "details": e.response.text}
        except Exception as e:
            return {"error": "Unknown error", "details": str(e)}

def print_result(data: Dict[str, Any], show_prompt: bool = False):
    """
    Hilfsfunktion zur sauberen Ausgabe des Responses.
    """
    # Kopie erstellen, um die Originaldaten nicht zu verändern
    output_data = json.loads(json.dumps(data))
    
    if not show_prompt and "results" in output_data:
        output_data["results"].pop("prompt", None)
    
    print(json.dumps(output_data, indent=2, ensure_ascii=False))


import plotly.express as px

def plot_emissions_plotly(df):
    # WICHTIG: Das Jahr in einen String umwandeln, 
    # damit Plotly es als Kategorie für die Gruppierung erkennt
    df_plot = df.copy()
    df_plot['jahr'] = df_plot['jahr'].astype(str)
    
    # Sortieren für saubere Darstellung
    df_plot = df_plot.sort_values(['bezeichnung', 'jahr'])
    
    fig = px.bar(
        df_plot, 
        x="bezeichnung", 
        y="wert_tco2", 
        color="jahr",
        barmode="group",      # Jetzt greift 'group' sicher
        title="Henkel THG-Emissionen: Vergleich der Jahre",
        labels={
            "wert_tco2": "Tonnen CO2e", 
            "bezeichnung": "Emissionsart", 
            "jahr": "Berichtsjahr"
        }
    )
    
    # Formatierung der Zahlen über den Säulen
    fig.update_traces(
        texttemplate='%{y:,.0f}', 
        textposition='outside',
        cliponaxis=False
    )
    
    fig.update_layout(
        xaxis_tickangle=-45,
        yaxis_type="linear",
        yaxis_tickformat=',.0f',
        legend_title_text='Jahr',
        # Korrigierte Properties:
        bargap=0.15,      # Abstand zwischen den Kategorien (z.B. zwischen Scope 1 und Scope 2)
        bargroupgap=0.1,  # Abstand zwischen den Säulen 2021 und 2024 innerhalb einer Gruppe
        height=800,
        margin=dict(b=200)
    )
    
    fig.show()

# --- Nutzung ---

config = {
  "generator_config": {
    "port": 8010,
    "mapping": [
      {"payload_key": "prompt", "target": ["question_selector", "user_query"]},
      {"payload_key": "collection", "target": ["search_qdrant", "collection_name"]},
      {"payload_key": "collection", "target": ["fetch_parents", "collection_name"], "suffix": "_parents"}
    ]
  }
}

client = PipelineClient(config)

#prompt="Wer sind die Autoren des papers im Context?", 
#collection="morals_markets"

#prompt = "Berichte aus dem Kontext alle Kennzahlen zu Treibhausgasemissionen (THG) von Henkel im Jahr 2021 und 2024! Berichte alle Werte in dem Schema {{Jahr}:{Bezeichnung und Geltungsbereich der Emissionen}:{Wert in tonnen CO2}}"

prompt = "Extrahiere aus dem Kontext alle Kennzahlen zu Treibhausgasemissionen (THG) von Henkel für 2021 und 2024. Wenn Kennzahlen zu Emissionen aufgegliedert werden, dann nehme alle Positionen der Untergliederung in deinen Output auf. Gib die Daten ausschließlich als valides JSON-Array zurück. Jedes Objekt im Array muss folgende Felder haben: 'jahr', 'bezeichnung' (inkl. Geltungsbereich) und 'wert_tco2' (als Zahl ohne Tausendertrennpunkt). Erzeuge keinen erklärenden Text vor oder nach dem JSON."
collection = "henkel_2024"

# Den Response in einer Variable auffangen
result = client.trigger_rag(
    prompt = prompt, 
    collection = collection
)

print("--- Rückgabe von RAG Request ---")
print_result(result, show_prompt=False)

raw_answer = result["results"]["answer"]
data = json.loads(raw_answer)
df = pd.DataFrame(data)
print(df)

plot_emissions_plotly(df)