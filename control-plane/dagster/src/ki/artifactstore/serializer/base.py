#ki/artifactstore/base.py

from typing import Any, Type, Optional, Union
from pathlib import Path
from abc import ABC, abstractmethod

class ArtifactSerializer(ABC):
    file_extension: str

    # --- Bestehende Dateisystem-Methoden (ArtifactStore) ---
    @abstractmethod
    def dump(self, obj: Any, path: Path) -> None:
        """Schreibt das Objekt direkt in eine Datei."""
        raise NotImplementedError

    @abstractmethod
    def load(self, path: Path, obj_type: Optional[Type] = None) -> Any:
        """Lädt das Objekt aus einer Datei."""
        raise NotImplementedError

    # --- Neue Memory-Methoden (Persistor / Live-Reporting) ---
    def serialize(self, obj: Any) -> Union[str, bytes]:
        """
        Wandelt das Objekt in eine Repräsentation im Speicher um.
        Gibt str für Text (JSON, CSV) oder bytes für Binärdaten (Numpy, Parquet) zurück.
        """
        raise NotImplementedError(f"Serializer {self.__class__.__name__} unterstützt keine Memory-Serialisierung.")

    def deserialize(self, data: Union[str, bytes], obj_type: Optional[Type] = None) -> Any:
        """Rekonstruiert das Objekt aus einem String oder Bytes."""
        raise NotImplementedError(f"Serializer {self.__class__.__name__} unterstützt keine Memory-Deserialisierung.")
