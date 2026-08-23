# ki/pipelines/sentiment/hfautoclassificationhead.py
# Encoding und Head für Sentiment-Klassifikation mit HF 
# AutoModelForSequenceClassification.from_pretrained

from ki.pipelines.sentiment.hfautotokenizer import Tokenized
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext

from pydantic import BaseModel
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, ClassVar
import torch
from transformers import AutoModelForSequenceClassification


class EncoderHeadConfig(BaseModel):
    hf_model_name: str = "distilbert-base-uncased-finetuned-sst-2-english"
    #Original:
    #hf_model_name: str = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"
    device: str = "cpu"
    return_logits: bool = True
    id2label: Optional[Dict[int, str]] = None
    label2id: Optional[Dict[str, int]] = None
    hidden_size: int = 768
    

class ResultPrediction(BaseComponentResult):
    labels: List[str]
    scores: List[float]
    logits: Optional[Any] = None
    true_labels: Optional[List[str]] = None
    _pipeline_outputs: ClassVar[List[str]] = ['labels', 'true_labels', 'scores', 'logits']


@dataclass
class EncoderHeadRunContext(BaseRunContext[EncoderHeadConfig]):
    component_name: str
    config: EncoderHeadConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   

@component_registry.register("hf_auto_classification_head")
class HFAutoClassificationHead(BaseComponent):

    CONFIG_CLASS = EncoderHeadConfig
    INPUT_CLASS = Tokenized
    OUTPUT_CLASS = ResultPrediction
    RUN_CONTEXT_CLASS = EncoderHeadRunContext  
   
    def __init__(
        self,
        *,
        config: EncoderHeadConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
    
        if self.config.device == "cpu":
            self.device = "cpu"
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Klassifikationsmodell laden
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.config.hf_model_name,
            label2id=self.config.label2id,
            id2label=self.config.id2label,
            ignore_mismatched_sizes=True    # war vorher auskommentiert
        )
        self.model.to(self.device)
        self.model.eval()

    def run(self, data: Tokenized, *, component_ctx = None, global_ctx = None) -> ResultPrediction:
        self.run_logger = global_ctx.run_logger
        
        with torch.no_grad():
            outputs = self.model(
                input_ids=data.input_ids.to(self.device),
                attention_mask=data.attention_mask.to(self.device)#,
                #token_type_ids=(
                 #   tokenized.token_type_ids.to(self.config.device)
                  #  if tokenized.token_type_ids is not None
                   # else None
                #)
            )

        logits = outputs.logits
        scores = torch.softmax(logits, dim=-1)

        # Maximalklassen bestimmen
        pred_ids = torch.argmax(scores, dim=-1).tolist()
        pred_scores = scores.max(dim=-1).values.tolist()
        pred_labels = [self.config.id2label[i] for i in pred_ids]

        pred = ResultPrediction(
            labels=pred_labels,
            scores=pred_scores,
            logits=logits.tolist() if self.config.return_logits else None,
            true_labels=data.true_labels,
            meta={**data.meta, "head": self.config.model_dump()}
        )

        return pred
