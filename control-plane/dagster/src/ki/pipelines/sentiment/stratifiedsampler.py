# ki/pipelines/sentiment/stratifiedsampler.py

from ki.pipelines.sentiment.rawtosentimentmapper import SentimentDocument
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext

from pydantic import BaseModel
from dataclasses import dataclass
from typing import List, Optional, ClassVar, Dict, Any
import pandas as pd
import numpy as np


class StratifiedSamplerConfig(BaseModel):
    limit: int = 20    
    seed: int = 42

class Preprocessed(BaseComponentResult):
    texts: List[str] = []
    true_labels: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None
    _drop_outputs: ClassVar[List[str]] = ["texts", "true_labels"]
    
    class ConfigDict:
        default_serializer = "pydantic_json"
    
@dataclass
class PreprocessedRunContext(BaseRunContext[StratifiedSamplerConfig]):
    component_name: str
    config: StratifiedSamplerConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   


@component_registry.register("stratified_sampler")
class StratifiedSampler(BaseComponent):
    CONFIG_CLASS = StratifiedSamplerConfig
    INPUT_CLASS = SentimentDocument
    OUTPUT_CLASS = Preprocessed 
    RUN_CONTEXT_CLASS = PreprocessedRunContext
    
    def __init__(
        self,
        *,
        config: StratifiedSamplerConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
    
    @staticmethod
    def stratified_sample(df, limit, seed):
        rng = np.random.default_rng(seed)
        label_col = "label"

        n_classes = df[label_col].nunique()
        n_per_class = max(1, limit // n_classes)

        frames = []
        for label, group in df.groupby(label_col):
            take = min(len(group), n_per_class)
            idx = rng.choice(len(group), size=take, replace=False)
            frames.append(group.iloc[idx])

        return pd.concat(frames, ignore_index=True)
        
    def run(self, data, *, component_ctx = None, global_ctx = None):
        self.run_logger = global_ctx.run_logger
        texts = data.texts
        labels = data.true_labels
        
        if labels is None:
            # Kein Sampling möglich, einfach Limit anwenden
            limit = min(self.config.limit, len(texts))
            sampled_texts = texts[:limit]
            sampled_labels = None
        else:
            limit = self.config.limit
            # Stratified Sampling
            df = pd.DataFrame({"text": texts, "label": labels})
            sampled_df = self.stratified_sample(df, limit=limit, seed=self.config.seed)
            sampled_texts = sampled_df["text"].tolist()
            sampled_labels = sampled_df["label"].tolist()

        preprocessed = Preprocessed(
            texts=sampled_texts,
            true_labels=sampled_labels,
            meta=data.meta
        )
        self.run_logger.info("Preprocessed: %d texts", len(sampled_texts))
        return preprocessed
