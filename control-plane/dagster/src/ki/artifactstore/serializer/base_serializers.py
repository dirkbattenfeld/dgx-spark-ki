# ki/artifactstore/serializer.base_serializer.py

from ki.artifactstore.serializer.registry import serializer_registry
from ki.artifactstore.serializer.base import ArtifactSerializer

from pathlib import Path
from typing import Any, Type, Optional, List, get_origin, get_args
import json
import io
import numpy as np
import pandas as pd


@serializer_registry.register("json")
class JsonSerializer(ArtifactSerializer):
    file_extension = ".json"

    def serialize(self, obj: Any) -> str:
        return json.dumps(
            obj, 
            indent=2, 
            ensure_ascii=False, 
            default=str 
        )
    
    def dump(self, obj: Any, path: Path) -> None:
        with path.open("w", encoding="utf-8") as f:
            f.write(self.serialize(obj))

    def load(self, path: Path, obj_type: Optional[Type] = None) -> Any:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)


@serializer_registry.register("pydantic_json")
class PydanticJsonSerializer(ArtifactSerializer):
    file_extension = ".json"

    def serialize(self, obj: Any) -> str:
        # Prüfen, ob es ein Pydantic-Modell ist (v2 nutzt model_dump, v1 dict)
        if hasattr(obj, "model_dump"):
            return json.dumps(obj.model_dump(mode='json'), indent=2, ensure_ascii=False)
        elif hasattr(obj, "dict"):
            return json.dumps(obj.dict(), indent=2, ensure_ascii=False)
        return json.dumps(obj, indent=2, ensure_ascii=False)

    def dump(self, obj: Any, path: Path) -> None:
        with path.open("w", encoding="utf-8") as f:
            f.write(self.serialize(obj))

    def load(self, path: Path, obj_type: Type) -> Any:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return obj_type(**data) if obj_type else data


@serializer_registry.register("pydantic_list_json")
class PydanticListJsonSerializer(ArtifactSerializer):
    file_extension = ".json"

    def serialize(self, obj: Any) -> str:
        def transform(item):
            # 1. Pydantic Modelle umwandeln
            if hasattr(item, "model_dump"):
                item = item.model_dump(mode='json')
            elif hasattr(item, "dict"):
                item = item.dict()

            # 2. Rekursion für Dictionaries (Wichtig!)
            if isinstance(item, dict):
                return {k: transform(v) for k, v in item.items()}
            
            # 3. Rekursion für Listen
            if isinstance(item, list):
                return [transform(i) for i in item]
            
            # 4. Path-Objekte umwandeln
            if isinstance(item, Path):
                return str(item)
                
            return item
        
        data = transform(obj)           
        return json.dumps(data, indent=2, ensure_ascii=False)

    def dump(self, obj: Any, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(self.serialize(obj))
    
    def load(self, path: Path, obj_type: Type = None) -> Any:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if obj_type is None:
            return data

        # Prüfung auf Generics wie list[MyModel] oder List[int]
        origin = get_origin(obj_type)
        args = get_args(obj_type)

        if origin in (list, List) or obj_type in (list, List):
            if args:  # Wenn ein Typ in der Liste definiert ist, z.B. list[User]
                item_type = args[0]
                # Nur konvertieren, wenn der item_type ein Pydantic-Modell o.ä. ist
                if hasattr(item_type, "__init__") and isinstance(data, list):
                    return [item_type(**item) if isinstance(item, dict) else item for item in data]
            return data

        # Einzelnes Objekt (Pydantic Modell)
        if hasattr(obj_type, "__init__") and isinstance(data, dict):
            return obj_type(**data)
        
        return data
    

@serializer_registry.register("numpy")
class NpySerializer(ArtifactSerializer):
    file_extension = ".npy"

    def serialize(self, obj: Any) -> bytes:
        buffer = io.BytesIO()
        np.save(buffer, obj)
        return buffer.getvalue()

    def dump(self, obj: Any, path: Path) -> None:
        np.save(path, obj)

    def load(self, path: Path, obj_type: Optional[Type] = None) -> Any:
        return np.load(path, allow_pickle=True)


@serializer_registry.register("pandas_parquet")
@serializer_registry.register("numpy_parquet")
class PandasParquetSerializer(ArtifactSerializer):
    file_extension = ".parquet"

    def dump(self, obj: Any, path: Path) -> None:
        if isinstance(obj, np.ndarray):
            # Numpy Array -> DataFrame (mit Spaltenname 'values')
            pd.DataFrame({"values": obj.flatten()}).to_parquet(path)
        elif isinstance(obj, pd.Series):
            name = obj.name if obj.name else "data"
            obj.to_frame(name=name).to_parquet(path)
        elif isinstance(obj, pd.DataFrame):
            obj.to_parquet(path)
        else:
            raise ValueError(f"Typ {type(obj)} wird nicht unterstützt.")

    def load(self, path: Path, obj_type: Optional[Type] = None) -> Any:
        df = pd.read_parquet(path)
        
        # Entscheidung basierend auf dem erwarteten Ziel-Typ (obj_type)
        if obj_type is np.ndarray:
            return df.values.flatten() # Zurück zu Numpy
        
        if obj_type is pd.Series or (len(df.columns) == 1 and obj_type != pd.DataFrame):
            return df.squeeze() # Zurück zu Series
        
        return df


@serializer_registry.register("pandas_csv")
class PandasCsvSerializer(ArtifactSerializer):
    file_extension = ".csv"

    def serialize(self, obj: pd.DataFrame) -> str:
        """Wandelt den DataFrame in einen CSV-String im Speicher um."""
        buffer = io.StringIO()
        # index=False ist meistens sauberer für den Datentransfer
        obj.to_csv(buffer, index=False)
        return buffer.getvalue()

    def dump(self, obj: pd.DataFrame, path: Path) -> None:
        """Schreibt wie bisher direkt auf die Festplatte."""
        obj.to_csv(path, index=False)

    def load(self, path: Path, obj_type: Optional[Type] = None) -> pd.DataFrame:
        return pd.read_csv(path)


import base64
from ki.core.datapipeline.datapipeline_dataclasses import Base64Image


@serializer_registry.register("base64_image")
class Base64ImageSerializer:
    file_extension = ".png"

    def serialize(self, obj: Base64Image) -> bytes:
        # Dekodiert den String zurück in rohe Bytes
        return base64.b64decode(obj.content)

    def dump(self, obj: Base64Image, path: Path) -> None:
        # Schreibt die dekodierten Bytes direkt in die Datei
        img_data = self.serialize(obj)
        with open(path, "wb") as f:
            f.write(img_data)

    def load(self, path: Path, obj_type: Optional[Type] = None) -> Base64Image:
        # Liest das Bild und wandelt es zurück in Base64 (falls nötig)
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode('utf-8')
        return Base64Image(content=encoded)
