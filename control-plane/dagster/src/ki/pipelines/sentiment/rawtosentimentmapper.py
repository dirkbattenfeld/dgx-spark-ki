# ki/pipelines/sentiment/rawtosentimentmapper.py

from ki.pipelines.sentiment.hfloader import RawDocument
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext

from pydantic import BaseModel
from typing import Optional, List, Dict, Any, ClassVar
from dataclasses import dataclass 


class RawToSentimentConfig(BaseModel):
    base_dir: str = "runs"
    label_map: dict = {0: "neg", 1: "pos"}

class SentimentDocument(BaseComponentResult):
    texts: List[str] = []
    true_labels: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None
    _drop_outputs: ClassVar[List[str]] = ["texts", "true_labels"]
    
    class ConfigDict:
        default_serializer = "pydantic_json"

@dataclass
class RawToSentimentRunContext(BaseRunContext[RawToSentimentConfig]):
    component_name: str
    config: RawToSentimentConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   

@component_registry.register("RawToSentiment")
class RawToSentimentMapper(BaseComponent):
    CONFIG_CLASS = RawToSentimentConfig
    INPUT_CLASS = RawDocument
    OUTPUT_CLASS = SentimentDocument
    RUN_CONTEXT_CLASS = RawToSentimentRunContext   
        
    def __init__(
        self,
        *,
        config: RawToSentimentConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
    
    def run(self, data, *, component_ctx = None, global_ctx = None):
        self.run_logger = global_ctx.run_logger
        labels = data.data.get("label")
        true_labels = [self.config.label_map[int(x)] for x in labels] if labels else None
        texts = data.data.get("text") or data.data.get("texts")
        
        sentiment_document=SentimentDocument(
            texts=texts,
            true_labels=true_labels,
            meta=data.data.get("meta")
        )

        self.run_logger.info(
            "Document: %d texts | labels present: %s",
            len(texts), true_labels is not None)
        
        return sentiment_document