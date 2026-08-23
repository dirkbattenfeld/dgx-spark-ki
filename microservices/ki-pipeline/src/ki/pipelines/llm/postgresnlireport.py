import os
import io
import base64
import pandas as pd
import matplotlib.pyplot as plt
from typing import Literal, ClassVar
from pydantic import BaseModel, ConfigDict
from dataclasses import dataclass
from sqlalchemy import create_engine, text

from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalRunContext, Base64Image
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.pipelines.llm.nlipostgreswriter import PostgresWriterResult

class PostgresNLIReportConfig(BaseModel):
    experiment_id: str
    table_name: str = "nli_evaluation_results"
    output_format: Literal["markdown", "json"] = "json"

class PostgresNLIReportResult(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    total_entries_analyzed: int
    avg_score: float
    report_df: pd.DataFrame             # Rohdaten inkl. berechnetem Score
    report_complete_df: pd.DataFrame    # Report über alle Experimente
    range_table: pd.Series              # Die Häufigkeitsverteilung
    plot_base64: Base64Image            # Das Histogramm als Bild-String
    _pipeline_outputs: ClassVar[list[str]] = ['total_entries_analyzed', 'avg_score', 'report_df', 'report_complete_df', 'range_table']

@dataclass
class PostgresNLIReportRunContext(BaseRunContext[PostgresNLIReportConfig]):
    component_name: str
    config: PostgresNLIReportConfig
    
    def __post_init__(self):
        super().__init__(component_name=self.component_name, config=self.config)

@component_registry.register("postgres_nli_report")
class PostgresNLIReport(BaseComponent):
    CONFIG_CLASS = PostgresNLIReportConfig
    INPUT_CLASS = PostgresWriterResult #als dummy
    OUTPUT_CLASS = PostgresNLIReportResult
    RUN_CONTEXT_CLASS = PostgresNLIReportRunContext

    def run(self, data, *, component_ctx: PostgresNLIReportRunContext, global_ctx: GlobalRunContext):
        run_logger = global_ctx.run_logger
        results_db_url = os.environ["RESULTS_DB_URL"]
        engine = create_engine(results_db_url)
        
        try:
            # gesamte Tabelle mit allen Experimenten einlesen            
            query_all = f"SELECT * FROM {component_ctx.config.table_name}"
            df_complete = pd.read_sql(text(query_all), con=engine)

            # Einträge zum aktuellen Experiment seletieren für ausführlichen Bericht
            df = df_complete[df_complete['experiment_id'] == component_ctx.config.experiment_id].copy()
            
            if df.empty:
                run_logger.warning(f"Keine Daten für Experiment {component_ctx.config.experiment_id} gefunden.")
                return PostgresNLIReportResult(
                    total_entries_analyzed=0, 
                    avg_score=0.0, 
                    report_df=pd.DataFrame(),
                    report_complete_df=pd.DataFrame(),
                    range_table=pd.Series(),
                    plot_base64=None
                )

            # NLI-Scoresaggregieren
            df['nli_aggregated_score'] = df['correct_diff'] - df['incorrect_diff']
            
            df['score_quality'] = df['total_score'].apply(
                lambda x: "High" if x > 0.8 else ("Medium" if x > 0.5 else "Low")
            )

            avg_score = float(df['total_score'].mean())

            # Histogramm erzeugen (im Speicher statt plt.show)
            plt.figure(figsize=(8,5))
            plt.hist(df['nli_aggregated_score'], bins=20, color='skyblue', edgecolor='black')
            plt.title(f'NLI Scores Distribution: {component_ctx.config.experiment_id}')
            plt.xlabel('Score')
            plt.ylabel('Count')
            plt.grid(axis='y', alpha=0.3)
            
            # Bild in Base64 umwandeln
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            plt.close() # Wichtig: Speicher freigeben
            plot_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            # Bereiche (Bins) definieren wie in deiner Vorlage
            bins = [-2, -1, -0.5, 0, 0.5, 1, 2]
            labels = ['-2 to -1', '-1 to -0.5', '-0.5 to 0', '0 to 0.5', '0.5 to 1', '1 to 2']
            
            df['range'] = pd.cut(df['nli_aggregated_score'], bins=bins, labels=labels, include_lowest=True)
            table = df['range'].value_counts().reindex(labels, fill_value=0)

            run_logger.info(f"Bericht zum Experiment {component_ctx.config.experiment_id} generiert für {len(df)} Einträge.")

            # Berechnung der Durchschnitte pro experiment_id
            stats = df_complete.groupby('experiment_id')[['total_score', 'correct_diff', 'incorrect_diff']].mean()
            # Optional: Index zurücksetzen, damit experiment_id eine normale Spalte wird
            stats = stats.reset_index()

            return PostgresNLIReportResult(
                total_entries_analyzed=len(df),
                avg_score=avg_score,
                report_df=df,
                report_complete_df=stats,
                range_table=table,
                plot_base64=Base64Image(content=plot_b64)
            )                              

        except Exception as e:
            run_logger.error(f"Fehler im PostgresReporter: {e}")
            raise
        finally:
            engine.dispose()