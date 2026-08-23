from typing import Any
from applications.rag.pipelines.rag_request.steps.configs import EmbedQueryConfig
from applications.rag.pipelines.rag_request.steps.models import QueryInput, EmbeddedQuery

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
