from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext
from ki.pipelines.sentiment.simplecleaner import Preprocessed2
from ki.pipelines.sentiment.hfautoclassificationhead import ResultPrediction

from pydantic import BaseModel
from dataclasses import dataclass
from transformers import pipeline
import torch
import os

class HFPipelineConfig(BaseModel):
    # Pfad zu deinem lokal gespeicherten ModernBERT Modell
    model_path: str = "modernbert_imdb_final"
    device: str = "cuda" # oder "cpu"
    batch_size: int = 16
    max_length: int = 512
    return_all_scores: bool = False

@dataclass
class HFPipelineRunContext(BaseRunContext[HFPipelineConfig]):
    component_name: str
    config: HFPipelineConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name, 
            config=self.config
        )

@component_registry.register("hf_sentiment_pipeline")
class HFSentimentPipeline(BaseComponent):
    """
    Ersetzt Tokenizer und Classification Head durch die optimierte HF-Pipeline.
    Nimmt Preprocessed2 (Texte) und gibt ResultPrediction (Labels/Scores) zurück.
    """
    CONFIG_CLASS = HFPipelineConfig
    INPUT_CLASS = Preprocessed2
    OUTPUT_CLASS = ResultPrediction
    RUN_CONTEXT_CLASS = HFPipelineRunContext

    def __init__(
        self,
        *,
        config: HFPipelineConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)

        # Mapping für Device-ID (HF Pipeline erwartet Integer für GPU oder -1 für CPU)
        device_id = 0 if self.config.device == "cuda" and torch.cuda.is_available() else -1

        # Sicherstellen, dass der Pfad absolut ist und existiert
        self.model_absolute_path = os.path.abspath(self.config.model_path)
        
        if not os.path.exists(self.model_absolute_path):
            raise FileNotFoundError(f"Modell-Pfad nicht gefunden: {self.model_absolute_path}")

        # Initialisierung der Pipeline
        # Lädt Modell und Tokenizer automatisch aus dem model_path
        self.classifier = pipeline(
            task="text-classification",
            model=self.model_absolute_path,
            tokenizer=self.model_absolute_path,
            device=device_id,
            batch_size=self.config.batch_size
        )

    def run(self, data: Preprocessed2, *, component_ctx = None, global_ctx = None) -> ResultPrediction:
        self.run_logger = global_ctx.run_logger

        # Die Pipeline kann direkt eine Liste von Strings verarbeiten
        # 'truncation=True' sorgt dafür, dass die max_length des Modells eingehalten wird
        pipe_results = self.classifier(
            data.texts,
            truncation=True,
            max_length=self.config.max_length
        )

        # Extraktion der Ergebnisse aus dem HF-Format: [{'label': 'positive', 'score': 0.99}, ...]
        pred_labels = [res['label'] for res in pipe_results]
        pred_scores = [res['score'] for res in pipe_results]

        return ResultPrediction(
            labels=pred_labels,
            scores=pred_scores,
            logits=None, # Die Pipeline gibt standardmäßig keine rohen Logits zurück
            true_labels=data.true_labels
        )

