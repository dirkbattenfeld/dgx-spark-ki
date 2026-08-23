# ki/pipelines/mlrunner/Scikitlearnmetrics.py

from dataclasses import dataclass
from typing import Optional, List, Dict, ClassVar
from pydantic import BaseModel
from sklearn import metrics

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.mlrunner.mlrunner import SciKitLearnResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext


class SciKitLearnMetricsConfig(BaseModel):
    task_type: str  # "classification" oder "regression"
    metrics_list: Optional[List[str]] = None  # zusätzliche optionale Metriken
    write_artifact: bool = True

class SciKitLearnMetricsResult(BaseComponentResult):
    results: Dict[str, float]
    _pipeline_outputs: ClassVar[list[str]] = ['results']   # Meta Datum: results gehört zum Output der Pipeline
    
    class ConfigDict:
        default_serializer = "pydantic_json"
        
@dataclass
class SciKitLearnMetricsRunContext(BaseRunContext[SciKitLearnMetricsConfig]):
    component_name: str
    config: SciKitLearnMetricsConfig
   
    def __post_init__(self):
        super().__init__(component_name=self.component_name, config=self.config)


@component_registry.register("sklearn_metrics")
class SciKitLearnMetrics(BaseComponent):

    CONFIG_CLASS = SciKitLearnMetricsConfig
    INPUT_CLASS = SciKitLearnResult  # Output der Modell-Komponente
    OUTPUT_CLASS = SciKitLearnMetricsResult
    RUN_CONTEXT_CLASS = SciKitLearnMetricsRunContext

    def run(self, data: SciKitLearnResult, *, component_ctx, global_ctx):

        y_true = data.y_test
        y_pred = data.predictions

        results: Dict[str, float] = {}

        # ---- Klassifikation oder Regression ----
        if component_ctx.config.task_type == "classification":
            results.update({
                "accuracy": metrics.accuracy_score(y_true, y_pred),
                "precision": metrics.precision_score(y_true, y_pred, zero_division=0),
                "recall": metrics.recall_score(y_true, y_pred, zero_division=0),
                "f1": metrics.f1_score(y_true, y_pred, zero_division=0),
            })
        elif component_ctx.config.task_type == "regression":
            results.update({
                "mse": metrics.mean_squared_error(y_true, y_pred),
                "rmse": metrics.mean_squared_error(y_true, y_pred, squared=False),
                "r2": metrics.r2_score(y_true, y_pred),
            })
        else:
            raise ValueError(f"Unknown task_type: {component_ctx.config.task_type}")

        # ---- Optional weitere Metriken ----
        if component_ctx.config.metrics_list:
            for m in component_ctx.config.metrics_list:
                if hasattr(metrics, m):
                    results[m] = getattr(metrics, m)(y_true, y_pred)

        # ---- Output-Datenobjekt erzeugen ----
        result = SciKitLearnMetricsResult(results=results)

        return result

# %%
