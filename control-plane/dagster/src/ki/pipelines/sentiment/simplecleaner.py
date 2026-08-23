# ki/pipelines/sentiment/simplecleaner.py
# Einfacher Cleaner für simples Text Cleaning

from ki.pipelines.sentiment.stratifiedsampler import StratifiedSamplerConfig
from ki.pipelines.sentiment.stratifiedsampler import Preprocessed
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext

from pydantic import BaseModel, ConfigDict
from dataclasses import dataclass
from typing import Dict, Any, List, ClassVar, Optional
import re

class CleanerConfig(BaseModel):
    lowercase: bool = True
    strip: bool = True
    remove_urls: bool = False
    remove_html: bool = False
    collapse_whitespace: bool = False

class Preprocessed2(BaseComponentResult):
    model_config = ConfigDict(coerce_numbers_to_str=True) # Erlaubt Int -> String
    texts: List[str] = []
    true_labels: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None
    _drop_outputs: ClassVar[List[str]] = ["texts", "true_labels"]
    
#    class ConfigDict:
#        default_serializer = "pydantic_json"
    
@dataclass
class CleanerRunContext(BaseRunContext[StratifiedSamplerConfig]):
    component_name: str
    config: StratifiedSamplerConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   


@component_registry.register("simple_cleaner")
class SimpleCleaner(BaseComponent):
    CONFIG_CLASS = CleanerConfig
    INPUT_CLASS = Preprocessed
    OUTPUT_CLASS = Preprocessed2 
    RUN_CONTEXT_CLASS = CleanerRunContext  

    def _clean_text(self, text: str) -> str:
        url_pattern = re.compile(r"http\S+")
        html_pattern = re.compile(r"<.*?>")
        whitespace_pattern = re.compile(r"\s+")
    
        if self.config.strip:
            text = text.strip()

        if self.config.lowercase:
            text = text.lower()

        if self.config.remove_urls:
            text = self.url_pattern.sub("", text)

        if self.config.remove_html:
            text = self.html_pattern.sub("", text)

        if self.config.collapse_whitespace:
            text = self.whitespace_pattern.sub(" ", text).strip()

        return text

    def run(self, data, *, component_ctx = None, global_ctx = None):
        self.run_logger = global_ctx.run_logger
        cleaned = [self._clean_text(t) for t in data.texts]
        return Preprocessed2(
            texts=cleaned,
            true_labels=data.true_labels,
            meta=data.meta,
        )
