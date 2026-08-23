from dataclasses import dataclass
from typing import List, Dict, ClassVar
from pydantic import BaseModel 

from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext, BaseRunContext

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.llm.questionselector import QuestionEntry
from ki.pipelines.llm.headpromptllm import HeadPromptLlmResult

from transformers import AutoModelForSequenceClassification, AutoConfig, pipeline

class NliEvaluatorConfig(BaseModel):
    model_name: str = "deberta"
    device: int = 0
    
@dataclass
class NliEvaluatorRunContext(BaseRunContext[NliEvaluatorConfig]):
    component_name: str
    config: NliEvaluatorConfig
    
    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )

class NliMetrics(BaseModel):
    correct_entailment_diff: float  # (Entailment - Contradiction)
    incorrect_entailment_diff: float
    total_score: float # Die Metrik aus deiner Notebook-Logik
    raw_scores: Dict[str, List[float]] # Die [E, N, C] Listen

class NliEvaluatorResult(BaseComponentResult):
    evaluation_results: Dict[int, NliMetrics]
    average_total_score: float
    entries_snapshot: List[QuestionEntry] 
    _pipeline_outputs: ClassVar[list[str]] = ['evaluation_results', 'average_total_score']

    class ConfigDict:
        default_serializer = "pydantic_json"


@component_registry.register("nli_evaluator")
class NLIModelEvaluator(BaseComponent):
    """
            Initialisiert einen NLI-Evaluator mit DeBERTa- oder RoBERTa-MNLI.
            Prüft beim Init die Klassifikationsgewichte.
            
            Args:
                model_name: 'deberta' oder 'roberta'
                device: CUDA device index, -1 für CPU
    """

    CONFIG_CLASS = NliEvaluatorConfig
    INPUT_CLASS = HeadPromptLlmResult
    OUTPUT_CLASS = NliEvaluatorResult
    RUN_CONTEXT_CLASS = NliEvaluatorRunContext
         
    def __init__(
        self,
        *,
        config: NliEvaluatorConfig,
        global_build_ctx: GlobalBuildContext):
     
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)      
            
        self.device = config.device
        self.model_name = config.model_name.lower()
        self.build_logger = global_build_ctx.build_logger
        
        if self.model_name == "deberta":
            self.nli_model_name = "microsoft/deberta-large-mnli"
        elif self.model_name == "roberta":
            self.nli_model_name = "roberta-large-mnli"
        else:
            raise ValueError("model_name must be 'deberta' or 'roberta'")
        
        # Gewicht-Check und Modell laden
        self._check_and_load_model()
    
    def _check_and_load_model(self):
        self.build_logger.info(f"Überprüfe Klassifikationsgewichte für {self.nli_model_name} ...")
        
        config = AutoConfig.from_pretrained(self.nli_model_name)
        model = AutoModelForSequenceClassification.from_pretrained(self.nli_model_name, config=config)
        
        model_keys = set(model.state_dict().keys())
        required_keys = {k for k in model_keys if "classifier" in k}
        missing_keys = [k for k in required_keys if k not in model_keys]
        
        if missing_keys:
            raise ValueError(f"FEHLENDE Klassifikationsgewichte: {missing_keys}")
        else:
            self.build_logger.info("Alle Klassifikationsgewichte sind geladen.")
        
        # Optional: nicht genutzte Checkpoint-Keys
        checkpoint_keys = set(AutoModelForSequenceClassification.from_pretrained(
            self.nli_model_name, config=config, ignore_mismatched_sizes=True
        ).state_dict().keys())
        unused_keys = checkpoint_keys - model_keys
        if unused_keys:
            print("Nicht genutzte Checkpoint-Keys:", unused_keys)
        
        # NLI-Pipeline bereitstellen
        self.nli_pipeline = pipeline(
            "text-classification",
            model=self.nli_model_name,
            tokenizer=self.nli_model_name,
            use_fast=True,
            top_k=None,
            device=self.device,
            return_all_scores=True
        )


    def _prepare_batch(self, entries: List[QuestionEntry]):
        batch_inputs = []
        mapping = []
        for idx, entry in enumerate(entries):
            # Nutzt deine bestehende Logik der Aggregation
            agg_correct = " </s> ".join(entry.correct_answers)
            agg_incorrect = " </s> ".join(entry.incorrect_answers)
            
            # Format: [Referenz] </s> [LLM Antwort]
            batch_inputs.append(f"{agg_correct} </s> {entry.llm_response}")
            batch_inputs.append(f"{agg_incorrect} </s> {entry.llm_response}")
            
            mapping.append((entry.index, "correct"))
            mapping.append((entry.index, "incorrect"))
        return batch_inputs, mapping

    def _calculate_metrics(self, raw_data: Dict[int, Dict]) -> Dict[int, NliMetrics]:
        results = {}
        for idx, scores in raw_data.items():
            c = scores.get('correct', [0, 0, 0])
            i = scores.get('incorrect', [0, 0, 0])
            
            c_diff = c[0] - c[2]
            i_diff = i[0] - i[2]
            
            results[idx] = NliMetrics(
                correct_entailment_diff=c_diff,
                incorrect_entailment_diff=i_diff,
                total_score=c_diff - i_diff,
                raw_scores={'correct': c, 'incorrect': i}
            )
        return results

    def run(self, data: HeadPromptLlmResult, *, component_ctx, global_ctx):
        run_logger = global_ctx.run_logger
        run_logger.info(f"Starte NLI-Batch-Evaluation für {len(data.entries)} Einträge.")

        # 1. Batch-Vorbereitung (ausgelagert)
        batch_inputs, mapping = self._prepare_batch(data.entries)
        
        # 2. GPU Inferenz
        raw_scores_map = {} # Zwischenspeicher: {index: {'correct': [E,N,C], ...}}
        max_batch_size = component_ctx.config.max_batch_size if hasattr(component_ctx.config, 'max_batch_size') else 16

        for i in range(0, len(batch_inputs), max_batch_size):
            batch = batch_inputs[i:i+max_batch_size]
            batch_results = self.nli_pipeline(batch, batch_size=len(batch))
            
            for res, (q_index, cat) in zip(batch_results, mapping[i:i+max_batch_size]):
                score_dict = {r['label'].upper(): r['score'] for r in res}
                e_n_c = [
                    float(score_dict.get("ENTAILMENT", 0.0)),
                    float(score_dict.get("NEUTRAL", 0.0)),
                    float(score_dict.get("CONTRADICTION", 0.0))
                ]
                if q_index not in raw_scores_map:
                    raw_scores_map[q_index] = {}
                raw_scores_map[q_index][cat] = e_n_c

        # 3. Metriken berechnen (ausgelagert)
        evaluation_results = self._calculate_metrics(raw_scores_map)
        
        # Durchschnitt berechnen
        avg_score = sum(m.total_score for m in evaluation_results.values()) / len(evaluation_results) if evaluation_results else 0.0

        run_logger.info(f"Evaluation beendet. Durchschnittlicher NLI-Score: {avg_score:.4f}")

        return NliEvaluatorResult(
            evaluation_results=evaluation_results,
            average_total_score=avg_score,
            entries_snapshot = data.entries
        )
