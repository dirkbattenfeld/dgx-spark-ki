 # Evaluiert Klassifikation
from ki.pipelines.sentiment.hfautoclassificationhead import ResultPrediction
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext, GlobalRunContext

from pydantic import BaseModel
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, ClassVar

from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix

class ClassificationEvaluatorConfig(BaseModel):
    pass

class Evaluation(BaseComponentResult):
    accuracy: float
    precision: float
    recall: float
    f1: float
    confusion: Optional[List[List[int]]] = None 
    meta: Optional[Dict[str, Any]] = None
    _pipeline_outputs: ClassVar[List[str]] = ['accuracy', 'precision', 'recall', 'f1', 'confusion']

@dataclass
class ClassificationEvaluatorRunContext(BaseRunContext[ClassificationEvaluatorConfig]):
    component_name: str
    config: ClassificationEvaluatorConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   


@component_registry.register("classification_evaluator")
class ClassificationEvaluator(BaseComponent):

    CONFIG_CLASS = ClassificationEvaluatorConfig
    INPUT_CLASS = ResultPrediction
    OUTPUT_CLASS = Evaluation
    RUN_CONTEXT_CLASS = ClassificationEvaluatorRunContext  

    def __init__(
        self,
        *,
        config: ClassificationEvaluatorConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
    
    def run(self, data: ResultPrediction, *, component_ctx: BaseRunContext = None, global_ctx: GlobalRunContext = None) -> Evaluation:
        self.run_logger = global_ctx.run_logger
        # Labels im Prediction Objekt
        y_true = data.true_labels
        y_pred = data.labels
    
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
        return evaluation

