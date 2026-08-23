from typing import Any
from applications.rag.pipelines.rag_request.configs import EmbedQueryConfig
from applications.rag.pipelines.rag_request.models import QueryInput, EmbeddedQuery
from libs.streampipe.observability import trace_action


@trace_action(step_name="embed")
async def embed_action(
    input_data: QueryInput, 
    infinity_client: Any, 
    config: EmbedQueryConfig
) -> EmbeddedQuery:
    """
    Nutzt die native, spezialisierte Async-Methode des InfinityClients.
    """
   
    vectors = await infinity_client.embeddings_async(
        texts=[input_data.prompt_query],
        model=getattr(infinity_client, "MODEL_EMBEDDING", "BAAI/bge-m3") # Fallback falls nicht gesetzt
    )
    dense_vector = vectors[0]

    return EmbeddedQuery(
        prompt_query=input_data.prompt_query,
        prompt_llm=input_data.prompt_llm,
        dense_vector=dense_vector,
        status="success"
    )
