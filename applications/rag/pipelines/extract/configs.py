from typing import Any, Dict, List
from pydantic import BaseModel, Field
  
class EmptyConfig(BaseModel):
        pass

class ExtractConfig(BaseModel):
    max_tokens: int = 8192
    temperature: float = 0.1
    no_think: bool = False
    max_context_chars: int = 100000
    max_chunks: int = 1
    system_prompt: str = (
        "Du bist ein Spezialist für die Extraktion von Nachhaltigkeitskennzahlen.\n"
        "Analysiere den bereitgestellten Textabschnitt und extrahiere alle relevanten Daten AUSSCHLIESSLICH auf Basis dieses Textes.\n"
        "Gib die extrahierten Daten AUSSCHLIESSLICH als valides JSON-Array zurück (eingebettet in einen YAML-Codeblock).\n"
        "Erzeuge KEINEN erklärenden Text vor oder nach dem Codeblock. Antworte nur mit den Daten.\n"
        "Wenn du keine passenden Kennzahlen findest, gib ein leeres Array `[]` zurück."
    )
    user_extraction_instruction: str = (
        "Extrahiere alle Kennzahlen zu Treibhausgasemissionen (THG) des Unternehmens für alle berichteten Jahre.\n" 
        "Wenn Kennzahlen zu Emissionen aufgegliedert werden, dann nehme alle Positionen der Untergliederung in deinen Output auf.\n"
        "Wenn Du zu einer Kennzahl keinen Wert findest, dann setze den wert auf 'NA'.\n"
        "Jedes Objekt im Array muss folgende Felder haben: 'jahr', 'bezeichnung' (inkl. Geltungsbereich) und 'wert' (als Zahl ohne Tausendertrennpunkt oder bei Prozentzahlen mit Komma)."
    )
    extras: Dict[str, Any] = Field(default_factory=dict)

class AggregateConfig(BaseModel):
    """
    Konfiguration für die aggregate_action.
    Hier werden die Schlüssel für die Deduplizierung definiert.
    """
    dedup_keys: List[str] = Field(default_factory=lambda: ["jahr", "bezeichnung"])
    extras: Dict[str, Any] = Field(default_factory=dict)
    
class ExportConfig(BaseModel):
    """
    Konfiguration für die export_excel_action.
    Definiert die Ziel-Endung für die Excel-Datei.
    """
    target_extension: str = ".xlsx"
    extras: Dict[str, Any] = Field(default_factory=dict)

