# ki/pipelines/sentiment/hfautotokenizer.py

from ki.pipelines.sentiment.simplecleaner import Preprocessed2
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext

from pydantic import BaseModel
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
# Tokenizer von HF mit AutoTokenizer.from_pretrained (für Sentimentanalyse)
from transformers import AutoTokenizer

class TokenizerConfig(BaseModel):
    hf_model_name: str = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"
    max_length: int = 512
    truncation: bool = True
    padding: str = "max_length"
    do_lower_case: bool = False
    add_special_tokens: bool = True
    return_attention_mask: bool = True
    return_token_type_ids: bool = False
    stride: int = 0
    pad_to_multiple_of: Optional[int] = None
    is_split_into_words: bool = False

class Tokenized(BaseComponentResult):
    input_ids: Any
    attention_mask: Optional[Any] = None
    token_type_ids: Optional[Any] = None
    true_labels: Optional[List[str]] = None
    meta: Dict[str, Any] = {}

@dataclass
class TokenizedRunContext(BaseRunContext[TokenizerConfig]):
    component_name: str
    config: TokenizerConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   


@component_registry.register("hf_auto_tokenizer")
class HFAutoTokenizer(BaseComponent):
    CONFIG_CLASS = TokenizerConfig
    INPUT_CLASS = Preprocessed2
    OUTPUT_CLASS = Tokenized
    RUN_CONTEXT_CLASS = TokenizedRunContext  
   
    def __init__(
        self,
        *,
        config: TokenizerConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
    
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.hf_model_name, do_lower_case=self.config.do_lower_case)
        
    def run(self, data, *, component_ctx = None, global_ctx = None):
        self.run_logger = global_ctx.run_logger
        encodings = self.tokenizer(
            data.texts,
            truncation=self.config.truncation,
            padding=self.config.padding,
            max_length=self.config.max_length,
            add_special_tokens=self.config.add_special_tokens,
            return_attention_mask=self.config.return_attention_mask,
            return_token_type_ids=self.config.return_token_type_ids,
            stride=self.config.stride,
            pad_to_multiple_of=self.config.pad_to_multiple_of,
            is_split_into_words=self.config.is_split_into_words,
            return_tensors="pt"
        )

        tokenized = Tokenized(
            input_ids=encodings["input_ids"],
            attention_mask=encodings["attention_mask"],
            token_type_ids=encodings.get("token_type_ids"),
            true_labels=data.true_labels,
            meta={"Metadaten": data.meta, "tokenizer": self.config.model_dump()}
        )

        return tokenized
    