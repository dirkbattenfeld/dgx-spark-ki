# ki/pipelines/sentiment/hfloader.py
# Standardloader für HuggingFace Datensätze von datasets

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext

from pydantic import BaseModel
from dataclasses import dataclass
from typing import Dict, Any, List, ClassVar
from datasets import load_dataset # Zum Laden von HuggingFace datasets 
import json
import yaml

class HFLoaderConfig(BaseModel):
    dataset_name: str = "imdb"
    split: str = "test"
    base_dir: str = "runs"

class RawDocument(BaseComponentResult):
    # Rohdaten aus HF Dataset
    data: Dict[str, Any] = {}  # komplette Spalten aus HF Dataset
    _drop_outputs: ClassVar[List[str]] = ["data"]

    class ConfigDict:
        default_serializer = "pydantic_json"

@dataclass
class HFLoaderRunContext(BaseRunContext[HFLoaderConfig]):
    component_name: str
    config: HFLoaderConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   

@component_registry.register("hf_loader")
class HFLoader(BaseComponent):
    ''' Downloaded den Datensatz von datasets, schreibt ihn ins Projektverzeichnis,
    lädt ab dem zweiten Aufruf aus dem Projektverzeichnis (= gecleanter Datensatzname)'''

    CONFIG_CLASS = HFLoaderConfig
    INPUT_CLASS = None
    OUTPUT_CLASS = RawDocument
    RUN_CONTEXT_CLASS = HFLoaderRunContext

    def __init__(
        self,
        *,
        config: HFLoaderConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
            
        # Projektverzeichnis nach Datensatzname
        self.base_path = global_build_ctx.base_path        
        self.data_path = self.base_path / "data" / "raw" / "data.json"      
        self.meta_path = self.base_path / "data" / "raw" / "meta.json"

    def run(self, data, *, component_ctx = None, global_ctx = None):
        self.run_logger = global_ctx.run_logger
        # Prüfen, ob Datensatz lokal gespeichert ist
        if self.data_path.exists():
            self.run_logger.info("Loading dataset from local file: %s", self.data_path)
            with open(self.data_path, "r") as f:
                data = json.load(f)
        else:
            self.run_logger.info("Downloading dataset: %s", component_ctx.config.dataset_name)
            ds = load_dataset(component_ctx.config.dataset_name, split=component_ctx.config.split)
            data = {col: list(ds[col]) for col in ds.column_names}
            
            # Metadaten sammeln
            meta = {
                "dataset_name": component_ctx.config.dataset_name,
                "split": component_ctx.config.split,
                "num_rows": len(ds),
                "columns": ds.column_names,
                "features": {k: str(v) for k, v in ds.features.items()},
            }
            
            # Vollständigen Datensatz mit Metadaten lokal speichern
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with open(self.meta_path, "w", encoding="utf-8") as f:
                yaml.dump(meta, f)   
            self.run_logger.info("Dataset saved locally: %s", self.data_path)
            self.run_logger.info("Metadata saved locally: %s", self.meta_path)         

        texts = data.get("text") or data.get("texts")  # Standardfeld für Pipeline
        raw_document = RawDocument(
            texts=texts,
            data=data,
            meta={"dataset": component_ctx.config.dataset_name, "split": component_ctx.config.split})
        
        return raw_document
