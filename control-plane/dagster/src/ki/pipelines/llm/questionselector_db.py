from ki.pipelines.llm.questionloader import Document
import os
import logging

from dataclasses import dataclass
from typing import List, Optional, ClassVar
from pydantic import BaseModel 

from sqlalchemy import create_engine, text

from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext, BaseRunContext, GlobalRunContext
from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent
from ki.pipelines.llm.questionselector import QuestionEntry, HeadPromptLlmInput

# todo: File lesen oder Testoption mit festen questions
# todo: Logik von RAG/Eval adaptieren mit batches und automatischer Fortsetzung  
# Konfigurationsklasse für TestQuestionLoader

class QuestionSelectorDBConfig(BaseModel):
    experiment_id: str  
    table_name: str = "nli_evaluation_results"
    batch_size: int = 1
    
@dataclass
class QuestionSelectorDBRunContext(BaseRunContext[QuestionSelectorDBConfig]):
    component_name: str
    config: QuestionSelectorDBConfig

    def __post_init__(self):
        super().__init__(
            component_name=self.component_name,
            config=self.config
        )
        
@component_registry.register("questionselector_db")
class QuestionSelectorDB(BaseComponent):    
    CONFIG_CLASS = QuestionSelectorDBConfig
    INPUT_CLASS = Document
    OUTPUT_CLASS = HeadPromptLlmInput
    RUN_CONTEXT_CLASS = QuestionSelectorDBRunContext

    def __init__(
        self,
        *,
        config: QuestionSelectorDBConfig,
        global_build_ctx: GlobalBuildContext):
         
        super().__init__(
            config=config,
            global_build_ctx=global_build_ctx)
        
        results_db_url = os.environ["RESULTS_DB_URL"]
        self.engine = create_engine(results_db_url)
    
    def get_last_processed_index(self, table_name: str, experiment_id: str, run_logger: logging) -> int:
        """Findet den höchsten question_index für das aktuelle Experiment."""
        query = text(f"SELECT MAX(question_index) FROM {table_name} WHERE experiment_id = :exp_id")
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query, {"exp_id": experiment_id}).scalar()
                return int(result) if result is not None else -1
        except Exception as e:
            # Falls die Tabelle noch nicht existiert oder leer ist
            run_logger.debug(f"Hinweis: Konnte Index nicht lesen (evtl. Tabelle noch leer?): {e}")
            return -1

    def run(self, data, *, component_ctx: QuestionSelectorDBRunContext, global_ctx: GlobalRunContext):
        config = component_ctx.config
        run_logger = global_ctx.run_logger
        
        # 1. Höchsten verarbeiteten Index aus DB holen
        last_index = self.get_last_processed_index(config.table_name, config.experiment_id, run_logger)
        start_index = last_index + 1
        
        entries = []
        # 2. Selektiere die nächsten batch_size Fragen aus dem Input-Dokument
        for i in range(start_index, start_index + config.batch_size):
            # Sicherheitscheck: Nicht über das Ende des Dokuments hinauslesen
            if i >= len(data.document):
                break
                
            raw = data.document[i]
            entries.append(QuestionEntry(
                index=i,
                question=raw["question"],
                correct_answers=raw.get("correct_answers", []),
                incorrect_answers=raw.get("incorrect_answers", []),
                type=raw.get("type", "unknown"),
                category=raw.get("category", "general")
            ))
            
        run_logger.info(f"DB-Selector: Starte bei Index {start_index}, Batch-Größe {len(entries)}")
        return HeadPromptLlmInput(entries=entries)
