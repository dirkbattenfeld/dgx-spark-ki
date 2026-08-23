import time
import logging
from typing import Any
from applications.rag.pipelines.rag_request.steps.configs import SearchQdrantConfig
from applications.rag.pipelines.rag_request.steps.models import EmbeddedQuery, SearchResult, SearchHit

logger = logging.getLogger("Pipeline.SearchQdrant")

async def search_action(
    input_data: EmbeddedQuery, 
    qdrant_service: Any, 
    config: SearchQdrantConfig
) -> SearchResult:
    """
    Asynchrone Action: Führt eine Vektorsuche auf Child-Chucks über den 
    asynchronen Client des DGX-SDK QdrantService aus.
    """
    start_time = time.time()
    hits = []
    status = "success"
    
    # Korrekte Nutzung des asynchronen Clients aus dem Service-Wrapper
    qdrant_client = qdrant_service.client
    
    #print(20*"-")
    #print("DEBUG search_action: \n")
    #print("Collection: ", config.collection_name)
    #print("limit: ", config.limit)
    #print("threshold: ", config.score_threshold)
    #print(20*"-")
     
    try:
        # Asynchroner Aufruf der Punktsuche
        raw_results = await qdrant_client.query_points(
            collection_name=config.collection_name,
            query=input_data.dense_vector,
            using="dense",
            limit=config.limit,
            score_threshold=config.score_threshold,
            with_payload=True,
        )

        sorted_points = sorted(
            raw_results.points, 
            key=lambda p: p.score, 
            reverse=True
        )
        
        hits = [
            SearchHit(
                id=str(p.id),
                score=p.score,
                text=p.payload.get("text", ""),
                context_preamble=p.payload.get("context_preamble"),
                rank=rank,
                meta={k: v for k, v in p.payload.items() if k not in ("text", "context_preamble")}
            )
            for rank, p in enumerate(sorted_points, start=1)
        ]
    
    except Exception as e:
        status = "error"
        logger.error(f"💥 Fehler bei Qdrant-Vektorsuche für Query '{input_data.query[:30]}...': {e}")
        print(f"💥 Qdrant-Suchfehler: {e}")

    duration = round(time.time() - start_time, 3)
    
    pipeline_metrics = {
        "hits_count": len(hits), 
        "search_duration_seconds": duration,
        "status": status
    }

    return SearchResult(
        prompt_query=input_data.prompt_query,
        prompt_llm=input_data.prompt_llm, 
        hits=hits, 
        status=status,
        extras=pipeline_metrics  
    )
