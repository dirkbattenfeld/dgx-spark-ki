import logging
from typing import Any
from applications.rag.pipelines.rag_request.steps.configs import ParentDocConfig
from applications.rag.pipelines.rag_request.steps.models import RerankResult, EnrichedResult, EnrichedHit

logger = logging.getLogger("Pipeline.FetchParents")

async def fetch_parents_action(
    input_data: RerankResult, 
    qdrant_service: Any, 
    config: ParentDocConfig
) -> EnrichedResult:
    """
    Asynchrone Action: Lädt basierend auf den Reranking-Treffern die zugehörigen
    Parent-Texte über den asynchronen Client des QdrantService nach.
    """
    enriched_hits = []
    status = "success"
    
    # Korrekte Nutzung des asynchronen Clients aus dem Service-Wrapper
    qdrant_client = qdrant_service.client if config.fetch_parent else None

    try:
        for rhit in input_data.hits:
            p_id = rhit.original_hit.meta.get(config.parent_id_field)
            p_text = None
            
            if config.fetch_parent and p_id and qdrant_client:
                # Asynchroner Punkt-Abruf über IDs
                res = await qdrant_client.retrieve(
                    collection_name=config.collection_name, 
                    ids=[str(p_id)], 
                    with_payload=True
                )
                if res: 
                    p_text = res[0].payload.get("text")
                                
            enriched_hits.append(
                EnrichedHit(
                    rerank_hit=rhit, 
                    parent_text=p_text, 
                    parent_id=p_id
                )
            )
            
    except Exception as e:
        status = "error"
        logger.error(f"💥 Fehler beim Laden der Parent-Dokumente aus Qdrant: {e}")
        print(f"💥 Qdrant-FetchParents-Fehler: {e}")

    pipeline_metrics = {
        "enriched_hits_count": len(enriched_hits),
        "status": status
    }

    return EnrichedResult(
        prompt_query=input_data.prompt_query,
        prompt_llm=input_data.prompt_llm, 
        hits=enriched_hits,
        status=status,
        extras=pipeline_metrics  
    )
