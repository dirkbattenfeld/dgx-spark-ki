# applications/rag/pipelines/rag_ingestion/pipeline.py

from typing import List, Type
from pydantic import BaseModel

from libs.pipeline.base import BasePipeline
from libs.pipeline.step import PipelineStep
from libs.pipeline.basemodels import BasePipelineEnv

from applications.rag.pipelines.rag_ingestion.config import RagIngestionConfig
from applications.rag.pipelines.rag_ingestion.environment import PdfIngestionEnv
from applications.rag.pipelines.rag_ingestion.steps.models import (
    ExtractInput,
    RawDocument,
    ChunkedDocument,
    EmbedOutput
)
from applications.rag.pipelines.rag_ingestion.steps.chunk import chunk_action
from applications.rag.pipelines.rag_ingestion.steps.contextualize import contextualize_action
from applications.rag.pipelines.rag_ingestion.steps.embed import embed_action
from applications.rag.pipelines.rag_ingestion.steps.extract import extract_action
from applications.rag.pipelines.rag_ingestion.steps.store import store_action


class RagIngestionPipeline(BasePipeline):
    """
    Kapselt das reine Manifest für die RAG Ingestion Pipeline.
    """
    @property
    def pipeline_id(self) -> str:
        return "rag_ingestion"

    @property
    def config_class(self) -> Type[BaseModel]:
        return RagIngestionConfig

    @property
    def initial_input_class(self) -> Type[BaseModel]:
        return ExtractInput

    def create_environment(self, config: RagIngestionConfig) -> BasePipelineEnv:
        return PdfIngestionEnv(config=config.env)

    def build_steps(self, config: RagIngestionConfig) -> List[PipelineStep]:
        step_cfgs = config.steps
        return [
            PipelineStep(
                name="Extract",
                input_class=ExtractInput,
                config=step_cfgs.extract,
                step_action=extract_action
            ),
            PipelineStep(
                name="Chunk",
                input_class=RawDocument,
                config=step_cfgs.chunk,
                step_action=chunk_action
            ),
            PipelineStep(
                name="Contextualize",
                input_class=ChunkedDocument,
                config=step_cfgs.contextualize,
                step_action=contextualize_action
            ),
            PipelineStep(
                name="Embeddings",
                input_class=ChunkedDocument,
                config=step_cfgs.embed,
                step_action=embed_action
            ),
            PipelineStep(
                name="StoreQdrant",
                input_class=EmbedOutput,
                config=step_cfgs.store,
                step_action=store_action
            )
        ]
