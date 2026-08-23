import optuna
import os 

from ki.core.nodeexecutor.dataclasses import UpstreamData
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalBuildContext, GlobalRunContext

from pydantic import BaseModel, ConfigDict
from dataclasses import dataclass
from typing import List, ClassVar
import pandas as pd


class OptunaStudyLoaderConfig(BaseModel):
    study_name: str 

class DF_OptunaStudy(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    study_names: List[str]
    df_study_results: pd.DataFrame 
    upstream_data: UpstreamData 
    _pipeline_outputs: ClassVar[List[str]] = ['df_study_results']

@dataclass
class OptunaStudyLoaderRunContext(BaseRunContext[OptunaStudyLoaderConfig]):
    component_name: str
    config: OptunaStudyLoaderConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )   

@component_registry.register("optuna_study_loader")
class OptunaStudyLoader(BaseComponent):
    ''' Lädt aus der Optuna PostgreSQL Datenbank die Optuna Study '''

    CONFIG_CLASS = OptunaStudyLoaderConfig
    INPUT_CLASS = UpstreamData
    OUTPUT_CLASS = DF_OptunaStudy
    RUN_CONTEXT_CLASS = OptunaStudyLoaderRunContext

    def __init__(
        self,
        *,
        config: OptunaStudyLoaderConfig,
        global_build_ctx: GlobalBuildContext):
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
        
        self.storage_url = os.environ["OPTUNA_DB_URL"]
        

    def run(self, data: UpstreamData = None, *, component_ctx: OptunaStudyLoaderRunContext, global_ctx: GlobalRunContext):
        run_logger = global_ctx.run_logger

        # Initialisierung der Liste
        study_names = []

        if data and data.has_data(): # Nutzt die neue has_data() Prüfung
            study_names = [
                node.node_config.generator_config.get("optuna_base", {}).get("study_name")
                for node in data.nodes
                if "optuna_base" in node.node_config.generator_config
            ]
            # Filtern von None-Werten, falls ein Key existiert aber leer ist
            study_names = [name for name in study_names if name]
            
            if study_names:
                run_logger.info(f"Load Optuna Study: Studiennamen ({study_names}) in Upstream-Daten gefunden.")

        # Wenn oben nichts gefunden wurde, nimm die Config
        if not study_names and component_ctx.config.study_name:
            study_names = [component_ctx.config.study_name]
            run_logger.info(f"Load Optuna Study: Es wird die Studie {study_names} aus der Config geladen.")

        # Finaler Check
        if not study_names:
            error_msg = "Load Optuna Study: Keine Studien zum Laden übergeben!"
            run_logger.error(error_msg)
            raise ValueError(error_msg)
        all_study_dfs = []

        for study_name in study_names:
            study = None
            try:
                study = optuna.load_study(
                    study_name=study_name, 
                    storage=self.storage_url
                )
                run_logger.info(f"Load Optuna Study: {study_name} erfolgreich geladen.")
                
                df = study.trials_dataframe()               
                df['study_name'] = study_name
                
                # Nur die 2 besten Werte (höchste 'value') behalten
                if not df.empty and 'value' in df.columns:
                    df = df.nlargest(2, 'value')
                
                all_study_dfs.append(df)

            except KeyError:
                run_logger.info(f"Load Optuna Study: Fehler, eine Studie mit dem Namen '{study_name}' wurde nicht gefunden.")
            except Exception as e:
                run_logger.info(f"Load Optuna Study: Ein Fehler ist aufgetreten beim Laden von {study_name}: {e}")

        # zusammenführen und sortieren
        if all_study_dfs:
            final_df = pd.concat(all_study_dfs, ignore_index=True)
            if 'value' in final_df.columns:
                final_df = final_df.sort_values(by='value', ascending=False)
        else:
            final_df = pd.DataFrame() # Fallback leeres DF

        result = DF_OptunaStudy(
            study_names=study_names,
            df_study_results=final_df,
            upstream_data = data)
      
        return result
