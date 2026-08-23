from typing import Any, Dict, List
import pandas as pd
from pydantic import Field, ConfigDict, field_serializer
from libs.streampipe.basemodels import BaseComponentResult

class ChunkExtraction(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    parent_id: str
    page_numbers: List[int] = Field(default_factory=list)
    raw_llm_output: str
    completion_tokens: int = 0
    extras: Dict[str, Any] = Field(default_factory=dict)

class ExtractResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: str
    extractions: List[ChunkExtraction] = Field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    model: str
    status: str = "success"
    extras: Dict[str, Any] = Field(default_factory=dict)

class ExtractedRecord(BaseComponentResult):
    """
    Repräsentiert einen einzelnen extrahierten Datensatz inklusive seiner 
    Metadaten zur lückenlosen Nachverfolgbarkeit (Herkunftsnachweis).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Dict[str, Any]             # Die eigentlichen extrahierten Nutzdaten (z.B. {"jahr": 2021, "wert": 100})
    parent_id: str                   # ID des Parent-Chunks aus dem Chunking-Schritt
    page_numbers: List[int] = Field(default_factory=list) # Liste der Seitenzahlen, aus denen der Text stammt
    extras: Dict[str, Any] = Field(default_factory=dict)

class AggregationInput(BaseComponentResult):
    """
    Eingangsdatenmodell für den Aggregations- und Deduplizierungsschritt.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    records: List[ExtractedRecord]   # Liste aller gesammelten Roh-Extrakte
    source_path: str = ""    
    extras: Dict[str, Any] = Field(default_factory=dict)
    
class AggregatedResult(BaseComponentResult):
    """
    Standardisiertes Ausgabe-Datenmodell der Aggregations-Action.
    Kapselt das Pandas DataFrame und liefert zusätzliche Metadaten für die Pipeline.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: pd.DataFrame               # Das aggregierte und deduplizierte DataFrame
    row_count: int = 0               # Anzahl der finalen Datensätze
    source_path: str = ""    
    status: str = "success"          # Status des Aggregationsschritts
    extras: Dict[str, Any] = Field(default_factory=dict) # Zusätzliche Metriken oder Informationen
    
    @field_serializer('data')
    def serialize_data(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Sorgt dafür, dass das DataFrame beim Serialisieren für das Logging 
        automatisch in eine JSON-kompatible Liste von Dictionaries konvertiert wird,
        ohne dass der Typ im Arbeitsspeicher für Folgeschritte verändert wird.
        """
        return data.to_dict(orient="records")