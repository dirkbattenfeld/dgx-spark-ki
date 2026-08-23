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
      
      
# %%
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
