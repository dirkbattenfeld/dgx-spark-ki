# ki/pipelines/sentiment/hfloader.py
# Standardloader für HuggingFace Datensätze von datasets

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext
from ki.pipelines.sentiment.simplecleaner import Preprocessed2

from pydantic import BaseModel
from typing import Optional, Dict
from dataclasses import dataclass
from datasets import load_dataset 

class HFLoaderConfig(BaseModel):
    dataset_path: str = "/app/projects/sentiment/data/processed/imdb_test.csv"
    limit: Optional[int]
    label_mapping: Dict[int, str] = {0: "negative", 1: "positive"}

@dataclass
class HFLoaderRunContext(BaseRunContext[HFLoaderConfig]):
    component_name: str
    config: HFLoaderConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   

@component_registry.register("csv_loader")
class CSVLoader(BaseComponent):
    ''' Downloaded den Datensatz von datasets, schreibt ihn ins Projektverzeichnis,
    lädt ab dem zweiten Aufruf aus dem Projektverzeichnis (= gecleanter Datensatzname)'''

    CONFIG_CLASS = HFLoaderConfig
    INPUT_CLASS = None
    OUTPUT_CLASS = Preprocessed2
    RUN_CONTEXT_CLASS = HFLoaderRunContext

    def __init__(
        self,
        *,
        config: HFLoaderConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
            

    def run(self, data, *, component_ctx = None, global_ctx = None):
        self.run_logger = global_ctx.run_logger
        
        dataset = load_dataset('csv', data_files={'test': self.config.dataset_path})
        test_data = dataset['test']
        
        # Limitierung anwenden, falls in der Config gesetzt
        if self.config.limit is not None and self.config.limit > 0:
            test_data = test_data.select(range(min(self.config.limit, len(test_data))))
            self.run_logger.info(f"Limiting dataset to {len(test_data)} samples.")

        extracted_texts = test_data["text"] 
        
        # Labels extrahieren und mappen
        if "label" in test_data.column_names:
            raw_labels = test_data["label"]
            # Hier wandeln wir 0 -> "negative" und 1 -> "positive" um
            string_labels = [self.config.label_mapping.get(int(l), str(l)) for l in raw_labels]
        else:
            string_labels = None

        return Preprocessed2(
            texts=extracted_texts,
            true_labels=string_labels,
            meta={"source": self.config.dataset_path, "count": len(extracted_texts)},
        )

