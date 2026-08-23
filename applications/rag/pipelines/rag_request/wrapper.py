# applications/rag/pipelines/rag_request/wrapper.py
# Wrappt die gesamte RAG Request pipeline, so dass sie über eine Registry
# mit einer factory gebaut werden kann und über eine generische FastAPIBridge
# bereitgestellt werden kann 
# Erwartet {"prompt_query": "Anfrage an Vectorstore", "prompt_llm": "Auftrag für LLM"}

import logging
from typing import Any, Literal, Optional, Type, Dict

from applications.rag.pipelines.rag_request.config import RagRequestConfig
from applications.rag.pipelines.rag_request.pipeline import RagRequestPipeline
from libs.pipeline.runner import BasePipelineRunner
from libs.pipeline.wrapper import BasePipelineWrapper

logger = logging.getLogger(__name__)


class RagRequestWrapper(BasePipelineWrapper):
    """
    Spezifischer Wrapper für die RAG Request Pipeline.
    """

    @property
    def pipeline_id(self) -> str:
        return "rag_request"

    @property
    def pipeline_class(self) -> Type[RagRequestPipeline]:
        return RagRequestPipeline

    @property
    def config_class(self) -> Type[RagRequestConfig]:
        return RagRequestConfig

    @property
    def mode(self) -> Literal["single", "streaming"]:
        return "single"

    async def prepare_payloads(
        self,
        runner: BasePipelineRunner,
        config: RagRequestConfig,
        incoming_payload: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        
        if not incoming_payload or "prompt_query" not in incoming_payload or "prompt_llm" not in incoming_payload:
            logger.error("❌ [SingleWrapper] Kein Payload übergeben. Im Single-Modus wird ein initialer Input mit den keys 'prompt_query' und 'prompt_llm' benötigt.")
            return []
        return [incoming_payload]


    async def process_results(
        self,
        raw_results: list[Any],
        config: RagRequestConfig,
    ) -> dict[str, Any]:
        
        # DEBUG
        from libs.observability.helper import format_dict_tree
        print("\nDEBUG (process_results / raw_results):","="*60)
        print(format_dict_tree(raw_results))
        print("\n", "="*60)
        # DEBUG

        # Status direkt aus der Struktur auslesen
        status_paths = [
            "EmbedQuery.status",
            "SearchQdrant.status",
            "RerankBGE.status",
            "FetchParents.status",
            "GenerateLLM.status",
        ]
        
        pipeline_status_dict = self.aggregate_statuses_from_paths(raw_results, status_paths)

        # Pfade definieren (funktioniert direkt auf der Liste)
        exclude_paths = {
            "EmbedQuery", 
            "SearchQdrant",
            "RerankBGE"
        }
        
        # Direkt filtern ohne Typkonvertierung/Merging!
        clean_results = self.filter_paths(raw_results, exclude_paths)

        # DEBUG
        print("\nDEBUG (process_results / clean_results):","="*60)
        print(format_dict_tree(clean_results))
        print("\n", "="*60)
        # DEBUG
        
        return {
            "results": clean_results,
            "pipeline_status": pipeline_status_dict,
        }
        