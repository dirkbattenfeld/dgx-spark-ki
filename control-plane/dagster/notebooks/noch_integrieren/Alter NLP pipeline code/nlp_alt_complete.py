# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.18.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
# !pip install plotly

# %%
# data_objects.py
import numpy as np
import pandas as pd
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
from pydantic import BaseModel
logger = logging.getLogger(__name__)

class JsonSaveMixin:
    @staticmethod
    def _serialize_value(x):
        """Konvertiert Einzelwerte in JSON-kompatible Formate."""
        if isinstance(x, torch.Tensor):
            return x.detach().cpu().tolist()
    
        if isinstance(x, np.ndarray):
            return x.tolist()
    
        if isinstance(x, (np.integer,)):
            return int(x)
    
        if isinstance(x, (np.floating,)):
            return float(x)
    
        return x


    def serialize(self, obj):
        """Rekursiv über dict/list/Objektstrukturen gehen und Tensors serialisieren."""
        if isinstance(obj, dict):
            return {k: self.serialize(v) for k, v in obj.items()}
    
        if isinstance(obj, list):
            return [self.serialize(v) for v in obj]
    
        return self._serialize_value(obj)

    def save_json_file(self, path: Path, data: dict):
        """
        Speichert die übergebenen Daten als json File
        unter dem übergebenen Pfad
        """
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def save_json(self, path: Path, exclude_keys: Optional[List[str]] = None):
        """
        Speichert das Objekt als JSON, optional bestimmte Keys ausschließen.
        
        :param path: Pfad, unter dem die Datei gespeichert wird
        :param exclude_keys: Liste von Feldnamen, die nicht gespeichert werden sollen
        """
        exclude_keys = exclude_keys or []
        data_to_save = {
            key: value
            for key, value in self.model_dump().items()
            if key not in exclude_keys
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2)
            
    def save_jsonl(self, path: Path, fields: List[str]):  
        lists = [getattr(self, field) for field in fields]
        length = len(lists[0])
        with open(path, "w") as f:
            for i in range(length):
                record = {field: lists[idx][i] for idx, field in enumerate(fields)}
                f.write(json.dumps(record) + "\n")

    def save_yaml(self, path: Path, data):
        with open(path, "w") as f:
            yaml.dump(data, f)


class BaseDocument(BaseModel, JsonSaveMixin):
    texts: List[str]
    meta: Dict[str, Any] = {}

    def log(self):
        logger.info(
            "Document: %d texts | labels present: %s",
            len(self.texts), self.true_labels is not None)


class RawDocument(BaseDocument, JsonSaveMixin):
    # Rohdaten aus HF Dataset
    data: Dict[str, Any] = {}  # komplette Spalten aus HF Dataset


class SentimentDocument(BaseDocument, JsonSaveMixin):
    true_labels: Optional[List[str]] = None  # optional, nur falls vorhanden


class TopicDocument(BaseDocument, JsonSaveMixin):
    true_labels: Optional[List[str]] = None  # optional, nur falls vorhanden


class Preprocessed(BaseModel, JsonSaveMixin):
    texts: List[str]
    true_labels: Optional[List[str]] = None  # optional, nur wenn der Datensatz Labels hat
    meta: Dict[str, Any] = {}

    def log(self):
        logger.info("Preprocessed: %d texts", len(self.texts))
        # Optional: Beispieltext für DEBUG
        if self.texts:
            logger.debug("Example preprocessed text: %s", self.texts[0])


class Tokenized(BaseModel):
    input_ids: Any
    attention_mask: Optional[Any] = None
    token_type_ids: Optional[Any] = None
    true_labels: Optional[List[str]] = None
    meta: Dict[str, Any] = {}

    def log(self):
        """
        Loggt Tokenizer-Statistiken nach der Erstellung des Objekts.
        Funktioniert mit Torch-Tensoren, NumPy-Arrays und Listen.
        """
        if self.input_ids is None or len(self.input_ids) == 0:
            logger.warning("Tokenized object contains no input_ids")
            return

        # Längen der Sequenzen berechnen
        lengths = []
        for seq in self.input_ids:
            try:
                # Torch-Tensor
                lengths.append(seq.size(0))
            except AttributeError:
                try:
                    # NumPy-Array
                    lengths.append(seq.shape[0])
                except AttributeError:
                    # Python-Liste
                    lengths.append(len(seq))

        avg_len = np.mean(lengths)
        min_len = np.min(lengths)
        max_len = np.max(lengths)

        # INFO: Zusammenfassung
        logger.info(
            "Tokenized object: %d sequences | avg tokens: %.2f | min: %d | max: %d",
            len(lengths), avg_len, min_len, max_len
        )

        # DEBUG: Beispielhafte Tokenisierung (erste Sequenz)
        first_input_ids = self._to_list_safe(self.input_ids[0])
        first_attention_mask = self._to_list_safe(self.attention_mask[0]) if self.attention_mask is not None and len(self.attention_mask) > 0 else None

        logger.debug(
            "Example tokenization (first sequence): input_ids=%s, attention_mask=%s",
            first_input_ids,
            first_attention_mask
        )

        # WARNUNG bei Truncation
        max_length = self.meta.get("tokenizer", {}).get("model_max_length")
        if max_length:
            truncated = sum(1 for l in lengths if l >= max_length)
            if truncated > 0:
                logger.warning(
                    "%d sequences were truncated to max length of %d tokens",
                    truncated, max_length
                )

    @staticmethod
    def _to_list_safe(x):
        """Konvertiert Tensor/NumPy/Listen in Python-Liste, falls möglich."""
        if x is None:
            return None
        if hasattr(x, "tolist"):
            return x.tolist()
        return x

        
class Embedded(BaseModel):
    embeddings: Any
    true_labels: Optional[List[str]] = None
    meta: Dict[str, Any] = {}

    def log(self):
        if self.embeddings is not None:
            try:
                shape = self.embeddings.shape
            except AttributeError:
                shape = "unknown"
            logger.info("Embedded: %d embeddings | shape: %s", len(self.embeddings), shape)

    def save(self, path):
        df_embeddings_head = pd.DataFrame(self.embeddings).head()
        df_embeddings_head.to_json(path / "embeddings_head.json", orient="columns", indent=2)

            
class Encoded(BaseModel, JsonSaveMixin):
    representations: Any                     # z.B. Tensor
    pooled: Optional[Any] = None             # optionaler Tensor
    true_labels: Optional[List[str]] = None
    meta: Dict[str, Any] = {}

    def log(self):
        if self.representations is not None:
            shape = getattr(self.representations, "shape", "unknown")
            logger.info("Encoding finished. hidden_states: %s", shape)
        
        if self.pooled is not None:
            pooled_shape = getattr(self.pooled, "shape", "unknown")
            logger.info("Pooled representation shape: %s", pooled_shape)
        
        if self.meta:
            logger.debug("Meta info: %s", self.meta)

    def save(self, path:Path):
        # große Repräsentationen → npz
        if self.representations is not None:
            np.savez_compressed(path / "representations.npz", representations=self.representations.cpu().numpy())

        # pooled → JSON
        if self.pooled is not None:
            np_pooled = self.pooled.cpu().numpy() if hasattr(self.pooled, "cpu") else self.pooled
            with open(path / "encoded_pooled.json", "w", encoding="utf-8") as f:
                json.dump({"pooled": np_pooled.tolist()}, f, indent=2)
        
        if self.meta:
            with open(path / "meta_encoded.yaml", "w", encoding="utf-8") as f:
                yaml.safe_dump(self.meta, f)


class Result(BaseModel, JsonSaveMixin):
    """Abstraktes Basismodell für Ergebnisse aller Heads."""
    meta: Dict[str, Any] = {} 


class ResultPrediction(Result):
    labels: List[str]
    scores: List[float]
    logits: Optional[Any] = None
    true_labels: Optional[List[str]] = None
    
    def log(self):
        if self.labels is not None:
            logger.info("Head finished. Produced %d predictions.", len(self.labels))
        else:
            logger.info("Head failed to produce predictions.")

    def save(self, path:Path):
        data = self.serialize(self.model_dump())
        self.save_json_file(path, data)
    

class ResultTopic(Result):
    """Speichert alle relevanten BERTopic-Ergebnisse."""
    topics: List[int]                             # Topic-ID für jedes Dokument
    topic_probs: Optional[List[List[float]]]      # Wahrscheinlichkeiten der Topics (falls berechnet)
    topic_info: Optional[List[Dict]]              # Ausgabe von topic_model.get_topic_info()
    topics_terms: Optional[Dict[int, List[str]]]  # Wichtige Terme pro Topic (aus get_topics())
    embeddings: Optional[List[List[float]]]       # Optionale Speicherung der Dokumenten-Embeddings

    def log(self):
        if self.topics is not None:
            logger.info("Head finished. Produced %d topics.", len(set(self.topics)))
        else:
            logger.info("Head failed to produce topics.")

    def save(self, path: Path):
        file_path = path / "results_topic.json"
        # Serialisierung
        data = self.model_dump()  # Pydantic 2.x Methode
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("ResultTopic saved to %s", file_path)
      

class Evaluation(BaseModel, JsonSaveMixin):
    accuracy: float
    precision: float
    recall: float
    f1: float
    confusion: Optional[List[List[int]]] = None 
    meta: Dict[str, Any] = None

    def log(self):
        """Protokolliert die Evaluationsergebnisse."""
        logger.info("Evaluation finished. Accuracy = %s", self.accuracy)
        logger.info("Precision = %s, Recall = %s, F1 = %s", self.precision, self.recall, self.f1)
        if self.confusion is not None:
            logger.info("Confusion matrix:\n%s", self.confusion)
        if self.meta:
            logger.debug("Meta info: %s", self.meta)

    def save(self, path: Path):
        """Speichert die Evaluationsergebnisse als JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)  # sicherstellen, dass das Verzeichnis existiert
        metrics = {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "confusion": self.confusion,
            "meta": self.meta,
        }
        self.save_json(path)


# %%
from typing import Optional, Type
from pathlib import Path
from pydantic import BaseModel

class BaseComponent:
    Config: Optional[Type[BaseModel]] = None

    def __init__(self, config: Optional[dict] = None, base_dir: Path = Path("runs")):
        # Gemeinsame Ablage
        self.run_dir = Path(base_dir)

        # Komponenten-spezifisches Unterverzeichnis, z. B. run_dir / "loader"
        comp_name = self.__class__.__name__.lower()
        self.component_dir = self.run_dir / comp_name
        self.component_dir.mkdir(parents=True, exist_ok=True)

        # Falls Subklasse Pydantic Config definiert
        if self.Config:
            cfg_dict = config or {}
            self.config = self.Config(**cfg_dict)
        else:
            self.config = config or {}

    def save_yaml_file(self, name: str, data: dict):
        path = self.component_dir / f"{name}.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)

    def save_json_file(self, name: str, data: dict):
        path = self.component_dir / f"{name}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


# %%
# registry.py

from typing import Dict, Type

class Registry:
    def __init__(self):
        self._registry: dict[str, type] = {}
    
    def register(self, key: str):
        def decorator(cls):
            self._registry[key] = cls
            return cls
        return decorator

    def get(self, key: str) -> type:
        if key not in self._registry:
            raise KeyError(f"Key '{key}' not registered")
        return self._registry[key]

component_registry = Registry()
prompt_registry = Registry() 

# %%
# interfaces.py
from abc import ABC, abstractmethod
from typing import Any
# from .data_objects import Document, Preprocessed, Tokenized, Embedded, Encoded, Prediction

class DataLoader(ABC):
    @abstractmethod
    def load(self) -> RawDocument:
        pass

class RawMapper(ABC):
    @abstractmethod
    def run(self, raw: RawDocument) -> BaseDocument:
        """Wandelt ein RawDocument in eine Task-spezifisches Document um"""
        pass

class Preprocessor(ABC):
    @abstractmethod
    def run(self, doc: BaseDocument) -> Preprocessed:
        pass

class Tokenizer(ABC):
    @abstractmethod
    def run(self, pre: Preprocessed) -> Tokenized:
        pass

class Embedding(ABC):
    @abstractmethod
    def run(self, pre: Preprocessed) -> Embedded:
        pass

class Encoder(ABC):
    @abstractmethod
    def run(self, tokenized: Tokenized) -> Encoded:
        pass

class Head(ABC):
    @abstractmethod
    def run(self, enc: Encoded) -> Result:
        pass

class Head_TopicModelling(Head):
    @abstractmethod
    def run(self, pre: Preprocessed, enc: Encoded) -> Result:
        pass

class Evaluator(ABC):
    @abstractmethod
    def run(self, result: Result) -> Evaluation:
        pass

class Persistor(ABC):
    @abstractmethod
    def save(self, obj: Any) -> None:
        """Speichert ein beliebiges Pipeline-Objekt."""
        raise NotImplementedError


# %%
# components/dataloaders.py
#from ..registry import DataLoaderRegistry
#from ..base_component import BaseComponent
#from ..interfaces import DataLoader
#from ..data_objects import Document
logger = logging.getLogger(__name__)

from typing import Optional
from pydantic import BaseModel


# Standardloader für HF Datensätze von datasets
from datasets import load_dataset
from pathlib import Path
import json
import logging

@component_registry.register("hf_loader")
class HFLoader(BaseComponent, DataLoader):
    ''' Downloaded den Datensatz von datasets, schreibt ihn ins Projetverzeichnis,
    lädt ab dem zweiten Aufruf aus dem Projektverzeichnis (= gecleanter Datensatzname)'''

    class Config(BaseModel):
        dataset_name: str = "yelp_polarity"
        split: str = "test"
        base_dir: str = "runs"

    def __init__(self, config: Optional[dict]=None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)
        # Projektverzeichnis nach Datensatzname
        sanitized_name = self.config.dataset_name.replace("/", "_")
        self.project_dir = Path(self.config.base_dir) / sanitized_name
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.data_path = self.project_dir / "data.json"
        self.meta_path = self.project_dir / "meta.json"

    def load(self) -> RawDocument:
        # Prüfen, ob Datensatz lokal gespeichert ist
        if self.data_path.exists():
            logger.info("Loading dataset from local file: %s", self.data_path)
            with open(self.data_path, "r") as f:
                data = json.load(f)
        else:
            logger.info("Downloading dataset: %s", self.config.dataset_name)
            ds = load_dataset(self.config.dataset_name, split=self.config.split)
            data = {col: list(ds[col]) for col in ds.column_names}
            
            # Metadaten sammeln
            meta = {
                "dataset_name": self.config.dataset_name,
                "split": self.config.split,
                "num_rows": len(ds),
                "columns": ds.column_names,
                "features": {k: str(v) for k, v in ds.features.items()},
            }
            
            # Vollständigen Datensatz mit Metadaten lokal speichern
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with open(self.meta_path, "w", encoding="utf-8") as f:
                yaml.dump(meta, f)   
            logger.info("Dataset saved locally: %s", self.data_path)
            logger.info("Metadata saved locally: %s", self.meta_path)         

        texts = data.get("text") or data.get("texts")  # Standardfeld für Pipeline
        raw_document = RawDocument(
            texts=texts,
            data=data,
            meta={"dataset": self.config.dataset_name, "split": self.config.split})
        #raw_document.log() true labels fehlen noch, also im Mapper?
        return raw_document


# %%
logger = logging.getLogger(__name__)

from pydantic import BaseModel
from typing import Optional

@component_registry.register("RawToSentiment")
class RawToSentimentMapper(BaseComponent, RawMapper):
    class Config(BaseModel):
        base_dir: str = "runs"
        label_map: dict = {0: "neg", 1: "pos"}
        
    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)
       
    def run(self, raw: RawDocument) -> SentimentDocument:
        labels = raw.data.get("label")
        true_labels = [self.config.label_map[int(x)] for x in labels] if labels else None
        texts = raw.data.get("text") or raw.data.get("texts")
        
        sentiment_document=SentimentDocument(
            texts=texts,
            true_labels=true_labels,
            meta=raw.meta)
        sentiment_document.log()
        return sentiment_document


@component_registry.register("RawToTopic")
class RawToTopicMapper(BaseComponent, RawMapper):

    class Config(BaseModel):
        base_dir: str = "runs"
        # Default für AG News
        label_map: dict = {
            0: "World",
            1: "Sports",
            2: "Business",
            3: "Sci/Tech"
        }

    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)

    def run(self, raw: RawDocument) -> TopicDocument:
        # Labels extrahieren (HF liefert ints)
        labels = raw.data.get("label")
        true_labels = (
            [self.config.label_map[int(x)] for x in labels] 
            if labels is not None 
            else None
        )

        # Texte extrahieren (einzelne oder mehrere Einträge)
        texts = raw.data.get("text") or raw.data.get("texts")

        topic_document = TopicDocument(
            texts=texts,
            true_labels=true_labels,
            meta=raw.meta
        )

        topic_document.log()
        return topic_document


# %%
# components/preprocessor_basic.py
# from interfaces import Preprocessor
# from data_objects import Document, Preprocessed
# from ..registry import PreprocessorRegistry
# from ..base_component import BaseComponent
logger = logging.getLogger(__name__)

from pydantic import BaseModel
from typing import Optional
import pandas as pd

@component_registry.register("stratified_sampler")
class StratifiedSampler(BaseComponent, Preprocessor):
    class Config(BaseModel):
        limit: int = 20           # Anzahl der Samples insgesamt
        seed: int = 42            # für Reproduzierbarkeit

    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)
    
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
        
    def run(self, doc: BaseDocument) -> Preprocessed:
        texts = doc.texts
        labels = doc.true_labels
        
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
            meta={**doc.meta}
        )
        
        preprocessed.save_json(self.component_dir / "sampled_dataset_meta", exclude_keys=["texts", "true_labels"])
        preprocessed.save_jsonl(self.component_dir / "sampled_dataset_data", fields=["texts", "true_labels"])
        preprocessed.log()
        return preprocessed
        

# Einfacher Cleaner für simples Text Cleaning
import re

@component_registry.register("simple_cleaner")
class SimpleCleaner(BaseComponent, Preprocessor):
    class Config(BaseModel):
        lowercase: bool = True
        strip: bool = True
        remove_urls: bool = False
        remove_html: bool = False
        collapse_whitespace: bool = False

    url_pattern = re.compile(r"http\S+")
    html_pattern = re.compile(r"<.*?>")
    whitespace_pattern = re.compile(r"\s+")

    def _clean_text(self, text: str) -> str:
        
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

    def run(self, pre: Preprocessed) -> Preprocessed:
        cleaned = [self._clean_text(t) for t in pre.texts]
        return Preprocessed(
            texts=cleaned,
            true_labels=pre.true_labels,
            meta=pre.meta,
        )


# %%
from pydantic import BaseModel
from typing import Optional
#from .base import BaseComponent
#from .interfaces import Tokenizer
#from .registries import TokenizerRegistry
#from .data_objects import Document, Tokenized
logger = logging.getLogger(__name__)


# Tokenizer von HF mit AutoTokenizer.from_pretrained (für Sentimentanalyse)
from transformers import AutoTokenizer

@component_registry.register("hf_auto_tokenizer")
class HFAutoTokenizer(BaseComponent, Tokenizer):

    class Config(BaseModel):
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
    
    def __init__(self, config: Optional[dict]=None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.hf_model_name, do_lower_case=self.config.do_lower_case)
        
    def run(self, pre: Preprocessed) -> Tokenized:
        encodings = self.tokenizer(
            pre.texts,
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

        self.save_json_file("tokenizer_config", self.config.model_dump())

        tokenized = Tokenized(
            input_ids=encodings["input_ids"],
            attention_mask=encodings["attention_mask"],
            token_type_ids=encodings.get("token_type_ids"),
            true_labels=pre.true_labels,
            meta={**pre.meta, "tokenizer": self.config.model_dump()}
        )

        tokenized.log()
        return tokenized


# %%
# components/embedding_dummy.py
#from ..registry import EmbeddingRegistry
#from ..base_component import BaseComponent
#from ..interfaces import Embedding
#from ..data_objects import Preprocessed, Embedded
logger = logging.getLogger(__name__)

from pydantic import BaseModel
from typing import Optional


# Embeddings mit SentenceTransformers
from sentence_transformers import SentenceTransformer
import pandas as pd

@component_registry.register("sentence_transformer")
class SentenceTransformerEmbedder(BaseComponent, Embedding):
    class Config(BaseModel):
        hf_model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"
                
    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)
        
        self.model = SentenceTransformer(
            self.config.hf_model_name
        )
        
    def run(self, preprocessed: Preprocessed) -> Embedded:
        document_embeddings = self.model.encode(preprocessed.texts, show_progress_bar=True)

        embedded = Embedded(
            embeddings=document_embeddings,
            true_labels=preprocessed.true_labels,
            meta={"model": getattr(self.model, "name_or_path", None)}
        ) 
        embedded.log()
        embedded.save(self.component_dir)
        return embedded


# Noch nicht getestet: Embeddings mit HF AutoTokenizer (-> Tokenizer? / redundant?) und AutoModel.from_pretrained 
from transformers import AutoTokenizer, AutoModel
import torch

@component_registry.register("hf_sentence_embedder")
class HFSentenceEmbedder(BaseComponent, Embedding):
    class Config(BaseModel):
        hf_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
        pooling: str = "mean"
        device: Optional[str] = None
        max_length: int = 128
        padding: str = "max_length"
        truncation: bool = True
        batch_size: int = 32
        fp16: bool = False
        log_example: bool = True
        cache_dir: Optional[str] = None
        use_fast_tokenizer: bool = True
        
    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)
        # Tokenizer + Model laden
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.config.hf_model_name,
            cache_dir=self.config.cache_dir,
            use_fast=self.config.use_fast_tokenizer
        )
        self.model = AutoModel.from_pretrained(
            self.config.hf_model_name,
            cache_dir=self.config.cache_dir
        )
        # Device setzen
        self.device = torch.device(self.config.device if self.config.device else ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model.to(self.device)

    def run(self, pre: Preprocessed) -> Embedded:
        inputs = self.tokenizer(
            pre.texts,
            truncation=self.config.truncation,
            padding=self.config.padding,
            max_length=self.config.max_length,
            return_tensors="pt"
        )
        
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            out = self.model(**inputs)
        
        last_hidden = out.last_hidden_state  # [B, L, H]
        
        if self.pooling == "mean":
            mask = inputs["attention_mask"].unsqueeze(-1)
            pooled = (last_hidden * mask).sum(1) / mask.sum(1)
        else:
            pooled = last_hidden[:, 0, :]
        
        embedded = Embedded(
            embeddings=pooled.cpu(),
            true_labels=pre.true_labels,
            meta={"model": getattr(self.model, "name_or_path", None)}
        )
        
        embedded.log()
        return embedded


# %%
# components/encoder_dummy.py
#from ..registry import EncoderRegistry
#from ..base_component import BaseComponent
#from ..interfaces import Encoder
#from ..data_objects import Tokenized, Encoded
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)


# Noch nicht produktiv genutzt: HF Encoder mit AutoModel.from_pretrained
from transformers import AutoModel
import torch

@component_registry.register("hf_transformer_encoder")
class HFTransformerEncoder(BaseComponent, Encoder):
    class Config(BaseModel):
        hf_model_name: str = "xlm-roberta-base"
        device: Optional[str] = None
        max_length: int = 128
        padding: str = "max_length"
        truncation: bool = True
        batch_size: int = 32
        fp16: bool = False
        cache_dir: Optional[str] = None
        use_fast_tokenizer: bool = True
        output_hidden_states: bool = False
        output_attentions: bool = False
        pooling: str = "cls"  # cls, mean, max
        layer: Optional[int] = None  # für Layer-Auswahl, None = letzte
        log_example: bool = True
    
    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)
        
        # Device bestimmen
        self.device = torch.device(
            self.config.device if self.config.device else ("cuda" if torch.cuda.is_available() else "cpu")
        )

        # Model laden
        self.model = AutoModel.from_pretrained(
            self.config.hf_model_name,
            cache_dir=self.config.cache_dir,
            output_hidden_states=self.config.output_hidden_states,
            output_attentions=self.config.output_attentions
        ).to(self.device)

        self.hidden_size = getattr(self.model.config, "hidden_size", 768)

    def run(self, tokenized:Tokenized) -> Encoded:
        if not hasattr(tokenized, "input_ids"):
            raise ValueError("Encoder expected Tokenized object (tokenizer stage missing or incompatible).")

        # Eingaben vorbereiten
        batch = {}
        for k in ("input_ids", "attention_mask", "token_type_ids"):
            v = getattr(tokenized, k, None)
            if v is not None:
                batch[k] = v.to(self.device)

        # Forward pass
        with torch.no_grad():
            out = self.model(**batch)

        last_hidden = out.last_hidden_state  # [B, L, H]

        # Layer-Auswahl
        if self.config.layer is not None:
            last_hidden = last_hidden[:, :, :]  # optional, hier könntest du spezifische Layer ziehen
            # Hinweis: für tatsächliche Layer-Auswahl ggf. output_hidden_states=True nötig
            if not self.config.output_hidden_states:
                raise ValueError("Layer-Auswahl erfordert output_hidden_states=True.")
 
            hidden_states = out.hidden_states
 
            if self.config.layer >= len(hidden_states):
                raise ValueError(
                    f"Layer {self.config.layer} existiert nicht. "
                    f"Modell hat {len(hidden_states)-1} Transformer-Layer."
                )
 
            last_hidden = hidden_states[self.config.layer]  # echtes Layer-Picking

        # Pooling
        if self.config.pooling == "mean":
            mask = batch["attention_mask"].unsqueeze(-1)
            pooled = (last_hidden * mask).sum(1) / mask.sum(1)
        elif self.config.pooling == "max":
            mask = batch["attention_mask"].unsqueeze(-1)
            last_hidden = last_hidden.masked_fill(mask == 0, float("-inf"))
            pooled, _ = last_hidden.max(1)
        else:  # cls
            pooled = last_hidden[:, 0, :]

        encoded = Encoded(
            representations=last_hidden.cpu(),
            pooled=pooled.cpu() if pooled is not None else None,
            true_labels=tokenized.true_labels,
            meta={
                "encoder": getattr(self.model, "name_or_path", None),
                "hidden_size": self.hidden_size,
                "pooling": self.config.pooling,
                "layer": self.config.layer,
            }
        )

        encoded.log()
        encoded.save(self.component_dir) 
        return encoded


# %%
#from ..registry import HeadRegistry
#from ..base_component import BaseComponent
#from ..interfaces import Head
#from ..data_objects import Encoded, Prediction

from typing import List, Optional
import numpy as np
from pydantic import BaseModel
logger = logging.getLogger(__name__)

# Head für topic Modelling mit BERTopic (umap, hdbscan) nach erfolgtem embedding
import umap
import hdbscan
from bertopic import BERTopic
import plotly

@component_registry.register("bertopic_head")
class BertopicHead(BaseComponent, Head_TopicModelling):

    class Config(BaseModel):
        # UMAP
        n_neighbors: int = 15           # Anzahl Nachbarn, die UMAP bei der Bildung der lokalen Struktur berücksichtigen soll (< Anzahl Documente).
        n_components: int = 5           # Anzahl der Dimensionen, auf die reduziert werden soll (oft 2 oder 5 für Visualisierung/Clustering)
        umap_metric: str = "cosine"     # Distanzmetrik für die Berechnung der Ähnlichkeit ('cosine' für Embeddings).
        random_state: int = 42
        # HDBSCAN
        min_cluster_size: int = 2       # min_cluster_size sollte kleiner oder gleich der Anzahl der Dokumente sein
        hdbscan_metric: str = "euclidean"
        prediction_data: bool = True
        # BERTopic
        language: str = "multilingual"
        calculate_probabilities: bool = True
        verbose: bool = True
        
    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)         
        self.umap_model = umap.UMAP(
            n_neighbors=self.config.n_neighbors,
            n_components=self.config.n_components,
            metric=self.config.umap_metric,
            random_state=self.config.random_state)
        
        self.hdbscan_model = hdbscan.HDBSCAN(
            min_cluster_size=self.config.min_cluster_size,
            metric=self.config.hdbscan_metric,
            prediction_data=self.config.prediction_data)
        
        self.topic_model = BERTopic(
            umap_model=self.umap_model,
            hdbscan_model=self.hdbscan_model,
            language=self.config.language,
            calculate_probabilities=self.config.calculate_probabilities,
            verbose=self.config.verbose)

        self.results: Optional[ResultTopic] = None
        
    def run(self, preprocessed: Preprocessed, embeddings: Embedded) -> ResultTopic:                      
        topics, probs = self.topic_model.fit_transform(preprocessed.texts, embeddings=embeddings.embeddings)       
       
        # Zeige die ersten paar Topics und ihre repräsentativen Wörter an
        display(self.topic_model.get_topic_info().head())

        # Intertopic Distance Map
        self.topic_model.visualize_topics()
        
        # Hierarchy View
        self.topic_model.visualize_hierarchy()
        
        # Topic Distribution for 1 document
        self.topic_model.visualize_distribution(probs[0])
        
        # ============================================================
        # STEP 8 — Optional Topic Optimization
        # Example: merge two topics or remove outliers
        
        # Example to remove outliers:
        # topics = topic_model.reduce_outliers(docs, topics)
        
        # Example to merge topics:
        # topic_model.merge_topics(docs, [2, 7])
        
        # ============================================================
        # STEP 9 — Custom Topic Labels
        # (example assigning new readable names)
        
        # topic_model.set_topic_label(0, "Politics & World News")
        # topic_model.set_topic_label(1, "Sports")
        # topic_model.set_topic_label(2, "Business & Finance")
        
        # Show updated labels:
        # topic_model.get_topic_info()
        
        # BERTopic Ergebnisse bereinigen / serialisierbar machen
        topic_info_df = self.topic_model.get_topic_info()
        topic_info_dict = topic_info_df.to_dict(orient="records")  # Liste von dicts

        topics_terms_raw = self.topic_model.get_topics()
        topics_terms_clean = {
            topic_id: [term for term, _ in terms]
            for topic_id, terms in topics_terms_raw.items()
        }
        
        # Ergebnisobjekt erstellen
        self.results = ResultTopic(
            topics=topics,
            topic_probs=probs if self.config.calculate_probabilities else None,
            topic_info=topic_info_dict,
            topics_terms=topics_terms_clean,
            embeddings=embeddings.embeddings if hasattr(embeddings, "embeddings") else None,
            meta={
                "n_documents": len(preprocessed.texts),
                "umap_config": {
                    "n_neighbors": self.config.n_neighbors,
                    "n_components": self.config.n_components,
                    "metric": self.config.umap_metric
                },
                "hdbscan_config": {
                    "min_cluster_size": self.config.min_cluster_size,
                    "metric": self.config.hdbscan_metric
                }
            }
        )
        self.results.log()
        self.results.save(self.component_dir)
        self.topic_model.save(self.component_dir / "bertopic_model")
        logger.info("BERTopic model saved as 'bertopic_model'")
        return self.results


# Encoding und Head für Sentiment-Klassifikation mit HF AutoModelForSequenceClassification.from_pretrained
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification

@component_registry.register("hf_auto_classification_head")
class HFAutoClassificationHead(BaseComponent, Head):

    class Config(BaseModel):
        hf_model_name: str = "distilbert-base-uncased-finetuned-sst-2-english"
        device: str = "cpu"
        return_logits: bool = True
        id2label: Optional[Dict[int, str]] = None
        label2id: Optional[Dict[str, int]] = None
        hidden_size: int = 768
        
    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)

        if self.config.device == "cpu":
            self.device = "cpu"
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Klassifikationsmodell laden
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.config.hf_model_name,
            label2id=self.config.label2id,
            id2label=self.config.id2label #,
            #ignore_mismatched_sizes=True
        )
        self.model.to(self.device)
        self.model.eval()

    def run(self, tokenized: Tokenized) -> ResultPrediction:
        with torch.no_grad():
            outputs = self.model(
                input_ids=tokenized.input_ids.to(self.device),
                attention_mask=tokenized.attention_mask.to(self.device)#,
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
            true_labels=tokenized.true_labels,
            meta={**tokenized.meta, "head": self.config.model_dump()}
        )

        pred.log()
        return pred


# Nutzt pipeline von HuggingFace mit integriertem Tokenizer, Encoder und Head
from transformers import pipeline

@component_registry.register("hf_pipeline")
class HuggingFacePipeHead(BaseComponent, Head):
    class Config(BaseModel):
        hf_model_name: str

    def __init__(self, config: Optional[dict] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)

        device = 0 if torch.cuda.is_available() else -1
        self.pipe = pipeline(
            "sentiment-analysis",
            model=self.config.hf_model_name,
            tokenizer=self.config.hf_model_name,
            device=device,
            truncation=True,
            max_length=512
        )

    def run(self, input_obj) -> ResultPrediction:
        # Texte extrahieren
        if hasattr(input_obj, "texts"):
            texts = input_obj.texts
        elif hasattr(input_obj, "input_ids"):
            raise ValueError("HF Pipeline Head erwartet Tokenized + Texte nicht als Tensor. Nutze `texts`-Attribut oder Preprocessor davor.")
        elif isinstance(input_obj, str):
            texts = [input_obj]
        elif isinstance(input_obj, list):
            texts = input_obj
        else:
            raise ValueError(f"Unsupported input type {type(input_obj)} for HF Pipeline Head")

        results = self.pipe(texts)

        labels: List[str] = [r["label"] for r in results]
        scores: List[float] = [float(r["score"]) for r in results]

        prediction = ResultPrediction(
            labels=labels,
            scores=scores,
            logits=None,  # Pipeline liefert keine logits
            true_labels=input_obj.true_labels,
            meta={"head": "hf_pipeline", **(getattr(input_obj, "meta", {}) or {})}
        )
        prediction.log()
        return prediction


# %%
from abc import ABC, abstractmethod
from typing import List, Dict, Any
logger = logging.getLogger(__name__)

# Evaluiert Klassifikation
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
import numpy as np

@component_registry.register("classification_evaluator")
class ClassificationEvaluator(BaseComponent, Evaluator):
    def __init__(self, config: Dict[str, Any] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)

    def run(self, pred: ResultPrediction) -> Evaluation:
        # Labels im Prediction Objekt
        y_true = pred.true_labels
        y_pred = pred.labels
    
        if y_true is None or y_pred is None:
            raise ValueError("true_labels or predicted labels not found in Prediction")
    
        # Optional: alle Labels als Strings, falls gemischt
        y_true = [str(x) for x in y_true]
        y_pred = [str(x) for x in y_pred]
    
        # Accuracy
        acc = accuracy_score(y_true, y_pred)
    
        # Precision, Recall, F1 (weighted)
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, average='weighted', zero_division=0
        )
    
        # Confusion Matrix
        all_labels = sorted(list(set(y_true) | set(y_pred)))  # alle Labels berücksichtigen
        conf_mat = confusion_matrix(y_true, y_pred, labels=all_labels)
    
        evaluation = Evaluation(
            accuracy=acc,
            precision=precision,
            recall=recall,
            f1=f1,
            confusion=conf_mat.tolist(),
            meta={"labels": all_labels}
        )
        evaluation.log()
        evaluation.save(self.component_dir / "metrics.json")
        return evaluation


# %%
#from ..registry import PersistorRegistry
#from ..base_component import BaseComponent
#from ..interfaces import Persistor
#from ..data_objects import ResultPrediction, Embedded, Encoded
from pydantic import BaseModel
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Einfacher Persistor (Predictions über Datenklasse)
@component_registry.register("json_persistor")
class JSONPersistor(BaseComponent, Persistor):

    def __init__(self, config: Dict[str, Any] = None, base_dir=None):
        super().__init__(config=config, base_dir=base_dir)

    class Config(BaseModel):
        result_file: str = "result"
        save_yaml_config: bool = True
        
    def save(self, pred: ResultPrediction):
        pred.save(self.component_dir / "prediction.json")


# %%
import yaml
from pathlib import Path
from typing import Any, Dict


class YamlLoader:
    """
    Verantwortlichkeiten:
    - Datei laden (Pfad → Text)
    - YAML parsen (Text → Dict)
    - Vorverarbeitung (optional erweiterbar)
    - Keine Abhängigkeit zu Pipeline, Factory oder Pydantic

    Erweiterbar durch:
    - Env-Variable-Substitution
    - Includes / !include
    - Validierung
    - Logging
    - Templates
    """

    def load(self, path: str | Path) -> Dict[str, Any]:
        """Öffentliche API: Pfad in finalen Config-Dict wandeln."""
        raw_text = self._read_file(path)
        raw_dict = self._parse_yaml(raw_text)
        processed_dict = self._postprocess(raw_dict)
        return processed_dict

    # ---------------------------------------------------------
    # interne Schritte – modularisiert, unabhängig voneinander
    # ---------------------------------------------------------

    def _read_file(self, path: str | Path) -> str:
        """Liest Dateiinhalt, ohne Parsing-Logik."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        return p.read_text(encoding="utf-8")

    def _parse_yaml(self, text: str) -> Dict[str, Any]:
        """Parst YAML-Text in ein Dict."""
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"YAML parsing error: {e}")

    def _postprocess(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hook für spätere Erweiterungen.
        Standard: keine Veränderung.
        Beispiele für Erweiterungen:
        - ${ENV}-Substitution
        - Includes
        - Defaults
        """
        return cfg


# %%
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

# ----------------------------
# 1. GLOBAL BUILD CONTEXT
# ----------------------------
# Pipeline-weite, statische Infrastruktur, einmal beim Build gesetzt
@dataclass #(frozen=True)  # später wieder aktivieren, wenn komplett in main initialisiert
class GlobalBuildContext:
    component_registry: Any                 # ComponentRegistry
    prompt_factory: Optional[Any] = None  # optional, kann pro Pipeline einheitlich sein
    prompt_registry: Optional[Any] = None
    base_dir: Path = None #entfernen wenn im Run Context
    defaults: Dict[str, Any] = field(default_factory=dict)  # z.B. Default-Config-Werte
    # weitere systemweite Build-Daten, z.B. Validatoren


# ----------------------------
# 2. COMPONENT SPEC (Build, komponentenspezifisch)
# ----------------------------
# Statische Definition einer Komponente innerhalb der Pipeline
@dataclass(frozen=True)
class ComponentSpec:
    name: str                             # z.B. "head_prompt_llm"
    cls: Type                             # Klassenobjekt, z.B. Head_prompt_llm
    config_class: Optional[Type] = None   # CONFIG_CLASS der Komponente
    input_class: Optional[Type] = None    # INPUT_CLASS
    output_class: Optional[Type] = None   # OUTPUT_CLASS
    run_context_class: Optional[Type] = None
    
    # Build-Zeit Parameter / Defaults
    config_values: Dict[str, Any] = field(default_factory=dict)
    base_dir: Optional[str] = None

# ----------------------------
# 3. GLOBAL RUN CONTEXT
# ----------------------------
# Pipeline-weite Parameter, die sich pro Run ändern können
@dataclass
class GlobalRunContext:
    run_dir: Path                         # z.B. aus Datasetname erzeugt
    verbose: bool = False
    logger: Optional[Any] = None

# ---------------------------------------------------
# 4. Component Run Interface (gibt pipeline an main)
# ---------------------------------------------------
@dataclass(frozen=True)
class ComponentRunInterface:
    """
    Minimal-Objekt, das nur die für Run relevanten Informationen enthält.
    """
    name: str
    run_context_class: Optional[Type] = None

from dataclasses import dataclass, field
from typing import Literal, Union, List
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
import requests
import time

# PromptConfig-Varianten je nach prompt_type
class SimplePrompt(BaseModel):
    prompt_type: Literal["simple"] = "simple"

class ContextPrompt(BaseModel):
    prompt_type: Literal["context"] = "context"
    context: str = "Answer the following question short without offering options!"

class ContextFreiPrompt(BaseModel):
    prompt_type: Literal["context_frei"] = "context_frei"
    context: str = "You are an expert and provide professional answers!"
    template_text: str = "Answer the following question based on the context: {context}. Question: {question}"

PromptConfig = Union[SimplePrompt, ContextPrompt, ContextFreiPrompt]

# LLM Config
class LlmConfig(BaseModel):
    device: str = "cpu"
    n_predict: int = 4096
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int = 1
    repeat_penalty: float = 1.0
    streaming: bool = False

# Konfigurationsklasse für Head_prompt_llm
class HeadPromptLlmConfig(BaseModel):
    prompt_type: str = "simple"
    devices: List[str] = ["gpu", "cpu"]
    llm_config: LlmConfig

# Input/Output Datenstruktur
class HeadPromptLlmInput(BaseModel):
    questions: List[str]

class HeadPromptLlmResult(BaseModel):
    responses: List[str]

# RunContext für HeadPromptLlm
@dataclass
class BaseRunContext:
    """
    Basisklasse für alle RunContexts.
    Enthält nur runweite, komponentenspezifische Zustände.
    """
    component_name: str
    
@dataclass
class HeadPromptLlmRunContext(BaseRunContext):
    prompt: PromptConfig = field(default_factory=SimplePrompt)
    llm_override: Optional[LlmConfig] = None


# %%
from langchain_core.prompts import PromptTemplate
import requests

from typing import Any, Dict, List, Optional, Mapping

#####################################
# Local LLaMA LLM Klasse
#####################################
# Minimal-Basisklasse LLM, nur damit LangChain die Instanz akzeptiert
class LLM:
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        raise NotImplementedError()

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {}

    @property
    def _llm_type(self) -> str:
        return "custom_llm"

class LocalLlamaLLM(LLM):
    endpoint: Optional[str] = None

    class Config:
        extra = "allow" #erlaubt in Pydantic dynamische Attribute

    def __init__(self, device: str = "cpu", config: LlmConfig = None):
        super().__init__()
        self.config = config or LlmConfig() # Default falls Config = None
        # Device-basiertes Endpoint-Mapping
        endpoints = {
            "gpu": "http://172.25.0.10:5001/completion",
            "cpu": "http://172.25.0.11:5000/completion",
        }
    
        endpoints_old = {
            "gpu": "http://llama-gpu:5001/completion",
            "cpu": "http://llama-cpu:5000/completion",
        }
        self.endpoint = endpoints.get(device, endpoints["cpu"])
        # Hyperparameter zentral aus config ziehen
        self.n_predict = config.n_predict
        self.temperature = config.temperature
        self.top_p = config.top_p
        self.top_k = config.top_k
        self.repeat_penalty = config.repeat_penalty
        self.streaming = config.streaming
        
    def _call(self, prompt: str, llm_override: Optional[LlmConfig] = None, stop: Optional[List[str]] = None) -> str:
        cfg = llm_override or self.config
        
        response = requests.post(
            self.endpoint,
            json={
                "prompt": prompt,
                "n_predict": cfg.n_predict,
                "temperature": cfg.temperature,
                "top_p": cfg.top_p,
                "top_k": cfg.top_k,
                "repeat_penalty": cfg.repeat_penalty,
                "streaming": cfg.streaming
            }
        )
        response.raise_for_status()
        data = response.json()
        return data.get("content", "")

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"endpoint": self.endpoint}

    @property
    def _llm_type(self) -> str:
        return "local_llama"

# Hilfsfunktion zum Säubern der Antwort des LLM
def clean_antwort_llm (antwort):
    clean_result = antwort.replace("Answer:", "").strip()
    return clean_result



# %%
class PromptFactory:
    def __init__(self, registry: Registry, logger=None):
        self.registry = registry
        self.logger = logger

    def build_prompt(self, config: HeadPromptLlmConfig):
        """
        Baut eine Prompt-Komponente für eine HeadPromptLlm-Komponente.
        Nutzt Buildtime LLM-Config aus config.
        """
        prompt_type = config.prompt_type
        
        prompt_cls = self.registry.get(prompt_type)
        if not prompt_cls:
            if self.logger:
                self.logger.warning(
                    "Registry %s: Prompt '%s' nicht gefunden!",
                    type(self.registry).__name__,
                    prompt_type,
                )
            return None

        # === NEU: nur llm_config übergeben, execute bekommt RunContext ===
        return prompt_cls(llm_config=config.llm_config)

prompt_factory = PromptFactory(prompt_registry)


# %%
@prompt_registry.register("simple")
class SimplePrompt:
    def __init__(self, llm_config: LlmConfig):
        # === NEU: Nur LLM-Parameter, kein Template mehr ===
        self.llm_config = llm_config
        self.llm = LocalLlamaLLM(device=self.llm_config.device, config=self.llm_config)

    def execute(self, question: str, prompt: PromptConfig, llm_override: Optional[LlmConfig] = None) -> str:  # === NEU: nur prompt + override ===
        # === NEU: Template erst hier bauen aus Runtime-Prompt ===
        template_text = "{question}"
        prompt_template = PromptTemplate(input_variables=["question"], template=template_text)
        full_prompt = prompt_template.format(question=question)
        # === NEU: LLM-Overrides anwenden, falls vorhanden ===
        llm_config = llm_override or self.llm_config
        return self.llm._call(full_prompt, llm_override=llm_override)
        

@prompt_registry.register("context")
class ContextPrompt:
    def __init__(self, llm_config: LlmConfig):
        self.llm_config = llm_config
        self.llm = LocalLlamaLLM(device=self.llm_config.device, config=self.llm_config)

    def execute(self, question: str, prompt: PromptConfig, llm_override: Optional[LlmConfig] = None) -> str:  # === NEU ===
        template_text = f"{prompt.context}{{question}}"
        prompt_template = PromptTemplate(input_variables=["context", "question"], template=template_text)
        full_prompt = prompt_template.format(context=prompt.context, question=question)
        llm_config = llm_override or self.llm_config
        return self.llm._call(full_prompt, llm_override=llm_override)


@prompt_registry.register("context_frei")
class ContextFreiPrompt:
    def __init__(self, llm_config: LlmConfig):
        self.llm_config = llm_config
        self.llm = LocalLlamaLLM(device=self.llm_config.device, config=self.llm_config)

    def execute(self, question: str, prompt: PromptConfig, llm_override: Optional[LlmConfig] = None) -> str:  # === NEU ===
        template_text = prompt.template_text
        prompt_template = PromptTemplate(input_variables=["context","question"], template=template_text)
        full_prompt = prompt_template.format(context=prompt.context, question=question)
        llm_config = llm_override or self.llm_config
        return self.llm._call(full_prompt, llm_override=llm_override)


# %%
# -----------------------------
# ComponentFactory
# -----------------------------
class ComponentFactory:
    def __init__(self, global_build_ctx: GlobalBuildContext):
        self.global_build_ctx = global_build_ctx

    # -------- Phase 1: Build ComponentSpecs --------
    def build_component_spec(self, node: dict | None) -> Optional[ComponentSpec]:
        if not node:
            return None
    
        comp_name = node.get("name")
    
        # Registry nur zur Existenzprüfung
        comp_cls = self.global_build_ctx.component_registry.get(comp_name)
        if not comp_cls:
            if self.logger:
                self.logger.warning(
                    "Registry %s: Component '%s' not found!",
                    type(self.global_build_ctx.component_registry).__name__,
                    comp_name,
                )
            return None
    
        # Config Dict der Komponente holen
        config_dict = node.get("config", {})
    
        return ComponentSpec(
            name=comp_name,
            cls=comp_cls,                 # Klassenreferenz OK
            config_values=config_dict,    # immer dict in Phase 1
        )

    def build_component_spec_list(self, nodes: List[dict]) -> List[ComponentSpec]:
        specs = []
        for node in nodes:
            spec = self.build_component_spec(node)
            if spec is not None:
                specs.append(spec)
        return specs

    def build_pipeline_specs(self, pipeline_cfg: dict) -> list[ComponentSpec]:
        """
        Phase 1 – Build ComponentSpecs (roh)
        - Dynamisch aus pipeline["components"]
        - Beliebige Anzahl von Komponenten gleichen Typs möglich
        - Keine festen Keys
        """
        specs: list[ComponentSpec] = []
    
        for node in pipeline_cfg.get("components", []):
            spec = self.build_component_spec(node)
            if spec:
                specs.append(spec)
    
        return specs

    
    # -------- Phase 2: Enrich ComponentSpecs from Registry and nodes: Config.dict --------   
    
    def enrich_component_spec(
        self,
        spec: ComponentSpec | None
        ) -> ComponentSpec | None:
        if spec is None:
            return None

        comp_cls = spec.cls

        # 1) Metadaten aus der Komponente ziehen
        config_class = getattr(comp_cls, "CONFIG_CLASS", None)
        input_class = getattr(comp_cls, "INPUT_CLASS", None)
        output_class = getattr(comp_cls, "OUTPUT_CLASS", None)
        run_context_class = getattr(comp_cls, "RUN_CONTEXT_CLASS", None)

        # 2) Defaults aus GlobalBuildContext anwenden
        defaults = self.global_build_ctx.defaults.get(spec.name, {})

        merged_config_dict = {}
        if isinstance(spec.config_values, dict):
            # YAML-Werte haben Vorrang, defaults werden nur ergänzt, wenn Key fehlt
            merged_config_dict.update(defaults)
            merged_config_dict.update(spec.config_values)
        else:
            # wenn keine YAML-Werte vorhanden, nur defaults
            merged_config_dict.update(defaults)

        # 3) Config-Objekt erstellen (Pydantic)
        config_obj = None
        if config_class:
            try:
                # Pydantic-Klasse oder normale Config-Klasse instanziieren
                config_obj = config_class(**merged_config_dict)
            except Exception as e:
                raise ValueError(
                    f"Invalid config for component '{spec.name}': {e}"
                ) from e
           
        return ComponentSpec(
            name=spec.name,
            cls=comp_cls,
            config_class=config_class,
            input_class=input_class,
            output_class=output_class,
            run_context_class=run_context_class,
            config_values=config_obj
        )

    def enrich_component_spec_list(
        self,
        specs: list[ComponentSpec]
        ) -> list[ComponentSpec]:
        return [
            self.enrich_component_spec(spec)
            for spec in specs
            if spec is not None
        ]

    def enrich_pipeline_specs(
        self,
        specs: list[ComponentSpec]
        ) -> list[ComponentSpec]:
        """
        Phase 2 – Specs anreichern
        - Fügt CONFIG_CLASS, INPUT_CLASS, OUTPUT_CLASS und defaults hinzu
        """
        return [
            self.enrich_component_spec(spec)
            for spec in specs
        ]
       

    # -------- Phase 3: Komponenten instanziieren --------  
    def instantiate_component(self, spec: ComponentSpec):
        """
        Phase 3 – ComponentSpec → Instanz
        """
        if spec is None:
            return None
    
        # Sicherheitscheck: Phase 2 muss gelaufen sein
        if spec.config_class and not isinstance(spec.config_values, spec.config_class):
            raise RuntimeError(
                f"Component '{spec.name}' was not enriched before instantiation"
            )
    
        return spec.cls(
            config=spec.config_values,
            global_build_ctx=self.global_build_ctx
        )
    
    def instantiate_pipeline(self, specs: list[ComponentSpec]) -> list[object]:
        """
        Phase 3 – ComponentSpec → Komponenteninstanzen
        - Reihenfolge wie in YAML
        - Mehrere gleiche Typen erlaubt
        """
        components: list[object] = []
    
        for spec in specs:
            components.append(self.instantiate_component(spec))
    
        return components


# %%
@component_registry.register("head_prompt_llm")
class Head_prompt_llm(BaseComponent, Head):    
    CONFIG_CLASS = HeadPromptLlmConfig
    INPUT_CLASS = HeadPromptLlmInput
    OUTPUT_CLASS = HeadPromptLlmResult
    RUN_CONTEXT_CLASS = HeadPromptLlmRunContext
    
    def __init__(self, config: HeadPromptLlmConfig, global_build_ctx: GlobalBuildContext = None):
        super().__init__(config=config, base_dir=global_build_ctx.base_dir)

        # PromptFactory setzen
        self.prompt_factory = global_build_ctx.prompt_factory
        if not self.prompt_factory:
            raise ValueError("PromptFactory instance must be provided")
        
        # Prompt-Objekt bauen über Factory
        self.prompt_obj = self.prompt_factory.build_prompt(self.config)
        
    def run(self, data, *, component_ctx, global_ctx):
        for question in data.questions:
            start = time.time()
            answer = clean_antwort_llm(self.prompt_obj.execute(
                question,
                component_ctx.prompt,
                component_ctx.llm_override))
            dauer = time.time() - start
            print("Dauer: ", dauer)
            print(answer)
        return HeadPromptLlmResult(responses=[answer])


# %%
from typing import Literal, List
from pydantic import BaseModel, Field

# todo: File lesen oder Testoption mit festen questions
# todo: Logik von RAG/Eval adaptieren mit batches und automatischer Fortsetzung  
# Konfigurationsklasse für TestQuestionLoader
class TestQuestionLoaderConfig(BaseModel):
    dummy: int

# RunContext für QuestionLoader
@dataclass
class QuestionLoaderRunContext(BaseRunContext):
    questions: List[str] = field(default_factory=list)
    # Optional kann hier später Overrides, Caches, Modellinstanzen etc. ergänzt werden

@component_registry.register("questionloader")
class QuestionLoader(BaseComponent):    
    CONFIG_CLASS = None #QuestionLoaderConfig
    INPUT_CLASS = None
    OUTPUT_CLASS = HeadPromptLlmInput
    RUN_CONTEXT_CLASS = None #QuestionLoaderRunContext
    
    def __init__(self, config: Optional[Dict] = None, global_build_ctx: GlobalBuildContext = None):
        super().__init__(config=config, base_dir=global_build_ctx.base_dir)
        
    def run(self, data, *, component_ctx = None, global_ctx = None):
        with open("./runs/TruthfulQA/TruthfulQA_formatted.json", "r") as f:
            readdata = json.load(f)
        questions = [readdata[i]["question"] for i in range(5,6)]   
        #questions = ["What is the capital of france?", "Who wrote pride and prejudice?"]
        return HeadPromptLlmInput(questions=questions)


# %%
# pipeline_engine.py
#from .registry import *
#from .data_objects import Document, Preprocessed, Tokenized, Embedded, Encoded, Prediction
#from .interfaces import DataLoader, Preprocessor, Tokenizer, EmbeddingModel, Encoder, Head, Persistor

import logging
from typing import Optional, Dict, Any
from pathlib import Path
import yaml
from typing import Dict
import os
token = os.getenv("HF_TOKEN", None)

class NLP_Pipeline:
    def __init__(self, config_path: Path, global_build_ctx: GlobalBuildContext): 
        #cfg = self.load_config(config_path)
        loader = YamlLoader()
        yaml_config = loader.load(config_path)

        root = yaml_config.get("pipeline", yaml_config)
        self.cfg = root 

        # Erst das Run-Verzeichnis bestimmen
        self.run_dir = self._determine_run_dir(yaml_config)
        
        # Logger in Datei
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        for h in list(logger.handlers):
            logger.removeHandler(h)
        log_path = self.run_dir / "pipeline.log"
        file_handler = logging.FileHandler(log_path)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.info("Run directory: %s", self.run_dir)
        
        # Factory erzeugen
        # nächste Zeile löschen, wenn in global_run_context verschoben
        global_build_ctx.base_dir = self.run_dir
        factory = ComponentFactory(global_build_ctx)
        # Phase 1: Specs bauen
        raw_specs = factory.build_pipeline_specs(root)
        # Phase 2: Specs anreichern
        self.pipeline_specs = factory.enrich_pipeline_specs(raw_specs)
        # Phase 3: Komponenten instanziieren
        self.components = factory.instantiate_pipeline(self.pipeline_specs)

        # **Speichern der Pipeline-Konfiguration**
        cfg_path = self.run_dir / "config.yaml"
        with open(cfg_path, "w") as f:
            yaml.dump(self.cfg, f)
        logger.info("Pipeline configuration saved to %s", cfg_path)

    
    def get_run_context_interface(self) -> List[ComponentRunInterface]:
        """
        Liefert ein Interface für den Experimentator / Orchestrator:
        - Liste von Komponenten
        - Nur Name und run_context_class
        """
        interface: List[ComponentRunInterface] = []

        for spec in self.pipeline_specs:
            interface.append(
                ComponentRunInterface(
                    name=spec.name,
                    run_context_class=spec.run_context_class
                )
            )

        return interface

    
    def _determine_run_dir(self, cfg_root):
        """
        Bestimmt das Run-Verzeichnis:
        - Sucht höchstes run_xxxx Verzeichnis
        - legt run_xxxx+1 an
        """
        base = Path("runs")
        base.mkdir(exist_ok=True)
        dataset_name = (
            cfg_root.get("loader", {})
                    .get("config", {})
                    .get("dataset_name")
            or cfg_root.get("loader", {}).get("name", "default")
        )
        project_dir = base / dataset_name
        project_dir.mkdir(exist_ok=True)

        # nächstes run-Verzeichnis
        existing_runs = [d for d in project_dir.iterdir() if d.is_dir() and d.name.startswith("run_")]
        if not existing_runs:
            next_run = project_dir / "run_0001"
        else:
            max_id = max(int(d.name.split("_")[1]) for d in existing_runs)
            next_run = project_dir / f"run_{max_id+1:04d}"
        next_run.mkdir(exist_ok=True)
        return next_run
        
    def _validate_run_specs(self):
        """
        Statische Validierung der Pipeline vor Ausführung
        """
        available_outputs: set[type] = set()

        for i, spec in enumerate(self.pipeline_specs):
            # INPUT_CLASS prüfen
            if spec.input_class is not None:
                if spec.input_class not in available_outputs:
                    raise RuntimeError(
                        f"Pipeline invalid at position {i} ({spec.name}): "
                        f"Required input {spec.input_class.__name__} not available. "
                        f"Available: {[c.__name__ for c in available_outputs]}"
                    )

            # OUTPUT_CLASS prüfen
            if spec.output_class is None:
                raise RuntimeError(
                    f"Component '{spec.name}' has no OUTPUT_CLASS defined"
                )

            available_outputs.add(spec.output_class)

    def run(self,*, 
            comp_run_contexts:Dict[str, Optional[BaseRunContext]],
            global_ctx: GlobalRunContext
           ):
        """
        Führt die Pipeline sequentiell aus.
        """
        print("DEBUG  pipeline run: ", comp_run_contexts)
        # 0. Pre-Run-Validierung
        self._validate_run_specs()

        # 1. Datapool initialisieren
        datapool: dict[type, object] = {}
        
        # 2. Komponenten iterieren
        for spec, component in zip(self.pipeline_specs, self.components):

            # ---- Input bestimmen ----
            if spec.input_class is None:
                input_data = None
            else:
                input_data = datapool[spec.input_class]

            # ---- RunContext der Komponente holen
            component_ctx = comp_run_contexts.get(spec.name)

            # ---- Komponente ausführen ----
            output = component.run(
                input_data,
                component_ctx=component_ctx,
                global_ctx=global_ctx,
            )

            # ---- Output validieren ----
            if not isinstance(output, spec.output_class):
                raise RuntimeError(
                    f"Component '{spec.name}' returned "
                    f"{type(output).__name__}, expected {spec.output_class.__name__}"
                )

            # ---- Output im Datapool ablegen ----
            datapool[spec.output_class] = output
            
        logger.info("Pipeline finished.")
        # ----------------------------------
        # 3. Ergebnis zurückgeben
        # ----------------------------------
        return datapool

# %%
from typing import Dict, Iterable, Optional, Type

class RunContextFactory:
    """
    Erzeugt RunContext-Instanzen aus ComponentRunInterface-Definitionen.
    """

    def __init__(self, interfaces: Iterable[ComponentRunInterface]):
        self._interfaces = tuple(interfaces)
        self._validate_interfaces()

    def _validate_interfaces(self) -> None:
        for interface in self._interfaces:
            cls = interface.run_context_class
            if cls is None:
                continue

            if not issubclass(cls, BaseRunContext):
                raise TypeError(
                    f"RunContextClass für '{interface.name}' "
                    f"muss von BaseRunContext erben."
                )

    def create_run_contexts(self) -> Dict[str, Optional[BaseRunContext]]:
        """
        Liefert ein Dict:
        component_name -> RunContext-Instanz | None
        """
        run_contexts: Dict[str, Optional[BaseRunContext]] = {}

        for interface in self._interfaces:
            if interface.run_context_class is None:
                run_contexts[interface.name] = None
            else:
                run_contexts[interface.name] = interface.run_context_class(
                    component_name=interface.name
                )

        return run_contexts


# %%
# ---------
# BUILDTIME
# ---------
global_build_ctx = GlobalBuildContext(
            component_registry = component_registry,
            prompt_factory = prompt_factory,
            prompt_registry = prompt_registry,
            defaults = {})

#global build context in pipeline und in Komponenten anwenden
pipeline = NLP_Pipeline("llm.yaml", global_build_ctx) 

# -------
# RUNTIME
# -------
#Alles run spezifische von ComponentConfig in ComponentRunContext (aus YAML lesen) verlagern

#base_dir / run_dir / project_dir etc. korrekt anwenden 
#auf Basis neuer flacher Struktur mit Metadaten Verkettung
#und nichts mehr einzeln übergeben, sondern im RunContext (global oder component)

#todo: Aus yaml lesen
global_run_ctx = GlobalRunContext(
    run_dir="./runs",
    verbose=True,
    logger=None)

run_interface = pipeline.get_run_context_interface()
run_context_factory = RunContextFactory(run_interface)

component_run_contexts = run_context_factory.create_run_contexts()

print(component_run_contexts)
#component_run_contexts["head_prompt_llm"].prompt.prompt_type = "simple"

#todo: run context Objekt defaults mit Werten für aktuellen run überschreiben 
#(bspw. Schleife zur Auswirkung von temperature)

results = pipeline.run(comp_run_contexts=component_run_contexts, 
                       global_ctx=global_run_ctx)

# %%
