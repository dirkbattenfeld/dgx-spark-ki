# ToDo: Zweite Tabelle pflegen, in der falls nicht vorhanden, ein Datensatz mit experiment_id und der kompletten Config abgelegt wird 

from dataclasses import dataclass
from typing import ClassVar, Literal
from pydantic import BaseModel 
import json
import pandas as pd
import os 
 
from datetime import datetime
from sqlalchemy import create_engine

from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext, GlobalRunContext
from ki.pipelines.llm.nlievaluator import NliEvaluatorResult

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult


class PostgresWriterConfig(BaseModel):
    experiment_id: str  
    table_name: str = "nli_evaluation_results"
    if_exists: Literal["fail", "replace", "append", "delete_rows"] = "append"

class PostgresWriterResult(BaseComponentResult):
    rows_written: int
    _pipeline_outputs: ClassVar[list[str]] = ['rows_written']

@dataclass
class PostgresWriterRunContext(BaseRunContext[PostgresWriterConfig]):
    component_name: str
    config: PostgresWriterConfig
    
    def __post_init__(self):
        super().__init__(component_name=self.component_name, config=self.config)

@component_registry.register("nli_postgres_writer")
class PostgresWriter(BaseComponent):

    CONFIG_CLASS = PostgresWriterConfig
    INPUT_CLASS = NliEvaluatorResult 
    OUTPUT_CLASS = PostgresWriterResult
    RUN_CONTEXT_CLASS = PostgresWriterRunContext

    def run(self, data: NliEvaluatorResult, *, component_ctx: PostgresWriterRunContext, global_ctx: GlobalRunContext):
        run_logger = global_ctx.run_logger
        
        # 1. Transformation in ein flaches Format für SQL
        rows = []
        for entry in data.entries_snapshot:
            metrics = data.evaluation_results.get(entry.index)
            if not metrics:
                continue
            
            rows.append({
                "experiment_id": component_ctx.config.experiment_id,
                "task_id": global_ctx.run_id, # Optional: Um Läufe zu trennen
                "question_index": entry.index,
                "question": entry.question,
                "answer": entry.llm_response,
                "total_score": metrics.total_score,
                "correct_diff": metrics.correct_entailment_diff,
                "incorrect_diff": metrics.incorrect_entailment_diff,
                "raw_scores": json.dumps(metrics.raw_scores),
                "created_at": datetime.now()
            })
        
        df = pd.DataFrame(rows)

        results_db_url = os.environ["RESULTS_DB_URL"]
        engine = create_engine(results_db_url)
        
        try:
            df.to_sql(
                name=component_ctx.config.table_name,
                con=engine,
                if_exists=component_ctx.config.if_exists,
                index=False,
                # 'method' hilft bei großen Batches (Performance-Boost)
                method='multi' 
            )
            run_logger.info(f"Datenbank-Writer: {len(df)} Zeilen erfolgreich gespeichert.")
        except Exception as e:
            run_logger.error(f"Datenbankfehler: {e}")
            raise
        finally:
            engine.dispose()

        return PostgresWriterResult(rows_written=len(df))
