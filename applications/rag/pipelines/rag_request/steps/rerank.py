import logging
from typing import Any
from applications.rag.pipelines.rag_request.steps.configs import RerankConfig
from applications.rag.pipelines.rag_request.steps.models import SearchResult, RerankResult, RerankHit

logger = logging.getLogger("Pipeline.Rerank")

async def rerank_action(
    input_data: SearchResult, 
    infinity_client: Any, 
    config: RerankConfig
) -> RerankResult:
    """
    Asynchrone Action: Führt das Reranking der Suchergebnisse über die native
    rerank_async Methode des InfinityClients aus.
    """
   
    # Early Exit, falls die Vektorsuche keine Dokumente geliefert hat
    if not input_data.hits:
        return RerankResult(
            prompt_query=input_data.prompt_query,
            prompt_llm=input_data.prompt_llm, 
            hits=[], 
            status="success"
        )

    status = "success"
    reranked_hits = []

    try:
        # 🚀 SDK-SPEZIFISCHER AUFRUF (Analog zu Deinem embeddings_async-Fix)
        # Nutzt exakt die Parameter aus Deiner Client-Spezifikation
        results = await infinity_client.rerank_async(
            query=input_data.prompt_query,
            documents=[h.text for h in input_data.hits],
            model="BAAI/bge-reranker-v2-m3",
            top_n=config.top_n
        )

        # Mappen der Ergebnisse: Das SDK liefert eine Liste von Dicts/Objekten 
        # mit den Keys 'index' und 'relevance_score'
        for rank, item in enumerate(results, start=1):
            idx = item["index"]
            score = item["relevance_score"]
            
            reranked_hits.append(
                RerankHit(
                    original_hit=input_data.hits[idx],
                    rerank_score=score,
                    rank=rank
                )
            )

    except Exception as e:
        status = "error"
        logger.error(f"💥 Fehler beim SDK Reranking für Query '{input_data.query[:30]}...': {e}")
        print(f"💥 SDK-Rerank-Fehler: {e}")

    # Hier bündeln wir die Metriken analog zur alten postprocess-Funktion
    pipeline_metrics = {
        "reranked_hits_count": len(reranked_hits),
        "status": status
    }

    return RerankResult(
        prompt_query=input_data.prompt_query,
        prompt_llm=input_data.prompt_llm,
        hits=reranked_hits, 
        status=status,
        extras=pipeline_metrics  
    )
