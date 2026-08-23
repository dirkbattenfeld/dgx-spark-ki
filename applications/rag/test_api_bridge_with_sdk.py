from libs.observability.helper import format_dict_tree

# test_sdk_bridge.py
import asyncio
import logging
import sys

# Passt den Import-Pfad bei Bedarf an deine Ordnerstruktur an
from libs.ki_dgxsdk.ki_sdk import DGX_Client  

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SDKTest")


async def test_sdk(endpoint_name: str, **kwargs):
    logger.info("=" * 60)
    logger.info("🧪 STARTE SDK-TEST FÜR ENDPOINT: %s", endpoint_name)
    logger.info("=" * 60)

    # 1. SDK-Client für den Service laden
    try:
        dgx_client=DGX_Client(use_dispatcher=True)
        client = dgx_client.get_client("rag_pipeline_service")
    except Exception as e:
        logger.error("❌ Fehler beim Initialisieren des SDK-Clients: %s", e)
        sys.exit(1)

    logger.info("🚀 Sende Aufruf via SDK call_async...")
    logger.info("📦 Flache Kwargs (User-Eingabe): %s", kwargs)

    try:
        # Die flachen Kwargs werden vom MappingClient entgegengenommen 
        # und mittels microservices.yaml tief geschachtelt injiziert.
        result = await client.call_async(endpoint_name, **kwargs)

        logger.info("=" * 60)
        logger.info("✅ SDK-TEST ERFOLGREICH BEENDET!")
        logger.info("Ergebnis-Zusammenfassung:\n\n%s", format_dict_tree(result))
        logger.info("=" * 60)

    except Exception as e:
        logger.exception("❌ Fehler beim SDK-Aufruf: %s", e)
               

if __name__ == "__main__":
    # Flache Test-Konfigurationen – genau so, wie ein Entwickler die Methode aufrufen würde
    PIPELINE_CONFIGS = {
        "rag_ingestion_single": {
            "source_path": "s3://office-test/03_Die Verfassung der Allmende.pptx",
            "collection_name": "test4"  # Mappt via YAML auf 'overrides.StoreQdrant.collection_name'
        },
        
        "rag_ingestion_streaming": {
            "s3_bucket": "office-test",
            "collection_name": "test4" 
        }, 
        
        "rag_request": {
            "prompt_query": "What is known about attention in LLMs?",
            "prompt_llm": (
                "Answer the following question only based on the literature in the prompt! "
                "Don't use the knowledge in your training data! Answer only in markdown format. "
                "Answer in short bullet points with references! Provide a bibliography"
            )
        }
    }

    # Gewünschte Pipeline auswählen
    pipeline_id = "rag_ingestion_streaming"

    # Flaches Kwargs-Dict laden
    kwargs = PIPELINE_CONFIGS.get(pipeline_id, {})

    asyncio.run(test_sdk(endpoint_name=pipeline_id, **kwargs))    
    
    