from typing import Type
from applications.rag.pipelines.rag_ingestion.wrapper import RagIngestionSingleWrapper, RagIngestionStreamingWrapper
from applications.rag.pipelines.rag_request.wrapper import RagRequestWrapper

from libs.pipeline.wrapper import BasePipelineWrapper

# Zentrale Mapping-Tabelle aller verfügbaren Pipelines.
# Wird beim Start der FastAPI-Bridge in die Registry geladen.
ENABLED_PIPELINES: dict[str, Type[BasePipelineWrapper]] = {
    "rag_ingestion_single": RagIngestionSingleWrapper,
    "rag_ingestion_streaming": RagIngestionStreamingWrapper,
    "rag_request": RagRequestWrapper
}
