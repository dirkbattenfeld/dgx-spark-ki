from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext, GlobalRunContext
from ki.core.nodeexecutor.dataclasses import NodeOverrides
from ki.pipelines.ml_eval.load_optuna_study import DF_OptunaStudy

from pydantic import BaseModel, ConfigDict
from dataclasses import dataclass
from typing import List, ClassVar
import pandas as pd


class AnalyzeOptunaStudyConfig(BaseModel):
    select_max_model_count: int = 2   # maximale Anzahl an Modellen, für die NodeConfigs für downstream Studien erstellt werden

@dataclass
class AnalyzeOptunaStudyRunContext(BaseRunContext[AnalyzeOptunaStudyConfig]):
    component_name: str
    config: AnalyzeOptunaStudyConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   

class AnalyzeOptunaStudyResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    df_study_best_results: pd.DataFrame 
    models_selected: List[str]
    override_node_configs: List[NodeOverrides]
    _pipeline_outputs: ClassVar[List[str]] = ['df_study_best_results', 'models_selected', 'override_node_configs']


@component_registry.register("analyze_optuna_study")
class AnalyzeOptunaStudy(BaseComponent):
    ''' Analysiert Dataframe mit mehreren OptunaStudies vom OptunaStudyLoader '''

    CONFIG_CLASS = AnalyzeOptunaStudyConfig
    INPUT_CLASS = DF_OptunaStudy
    OUTPUT_CLASS = AnalyzeOptunaStudyResult
    RUN_CONTEXT_CLASS = AnalyzeOptunaStudyRunContext

    def __init__(
        self,
        *,
        config: AnalyzeOptunaStudyConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
        
    def run(self, data: DF_OptunaStudy, *, component_ctx: AnalyzeOptunaStudyRunContext, global_ctx: GlobalRunContext):
        run_logger = global_ctx.run_logger

        df = data.df_study_results

        best_per_study = (
            df.sort_values("value", ascending=False)
            .groupby("study_name")
            .head(1)
            )
    
        final_selection = best_per_study.sort_values("value", ascending=False).head(component_ctx.config.select_max_model_count)

        study_names_list = final_selection["study_name"].unique().tolist()
        run_logger.info(f"Analyze Optuna Study: Die Studies {study_names_list} wurden selektiert zur Fortsetzung.")

        overrides = []
        overrides_node_id = []
        for entry in data.upstream_data.nodes:
            if entry.node_config.generator_config["optuna_base"]["study_name"] in study_names_list:
                override = NodeOverrides(**entry.node_config.model_dump())   # derzeit wird noch die unveränderte Node Config als Override übergeben
                overrides.append(override)
                overrides_node_id.append(override.node_id)
        run_logger.info(f"Analyze Optuna Study: Die Node Configs mit den Node Ids {overrides_node_id} wurde(n) als Override übergeben.")

        result = AnalyzeOptunaStudyResult(
            df_study_best_results = final_selection, 
            models_selected = study_names_list,
            override_node_configs = overrides)
                                
        return result
