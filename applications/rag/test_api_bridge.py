# test_api_bridge.py
import httpx
import sys
import logging
import asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("APITest")

BASE_URL = "http://100.67.8.64:8011/api/v1/pipelines"

async def test_api(pipeline_id: str, payload: dict, overrides: dict):
    logger.info("=" * 60)
    logger.info("🧪 STARTE HTTP-API TEST (%s)", BASE_URL)
    logger.info("=" * 60)    
    
    run_url = f"{BASE_URL}/run"
    
    request_body = {
        "pipeline_id": pipeline_id,
        "payload": payload,
        "overrides": overrides
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        # 1. Pipeline-Liste abrufen (wie es das Chainlit Frontend macht)
        logger.info(f"📡 Rufe verfügbare Pipelines ab: GET {BASE_URL}/")
        
        try:
            response = await client.get(f"{BASE_URL}/")
            response.raise_for_status()
            data = response.json()
            logger.info(f"✅ Verfügbare Pipelines: {data}")
        except httpx.ConnectError:
            logger.info("❌ Verbindung zur FastAPI Bridge fehlgeschlagen! Läuft der Server auf Port 8011?")
            sys.exit(1)
        except Exception as e:
            logger.info(f"❌ Fehler beim Abrufen der Pipelines: {e}")
            sys.exit(1)
        
        logger.info("🚀 Sende POST-Request an: %s", run_url)
        logger.info("📦 Payload: %s", payload)
        logger.info("⚙️ Overrides: %s", overrides)
        
        try:
            response = await client.post(run_url, json=request_body)
            
            if response.status_code == 200:
                logger.info("=" * 60)
                logger.info("✅ API-TEST ERFOLGREICH BEENDET! (Status: %s)", response.status_code)
                logger.info("Ergebnis-Zusammenfassung: %s", response.json())
                logger.info("=" * 60)
            else:
                logger.error("❌ API antwortete mit Fehler-Code [%s]: %s", response.status_code, response.text)

        except httpx.RequestError as e:
            logger.error("❌ Verbindungsfehler zum API-Server: %s", e)
        except Exception as e:
            logger.exception("❌ Unerwarteter Fehler beim API-Aufruf: %s", e)


if __name__ == "__main__":
    # Dict mit Konfigurationen je Pipeline
    PIPELINE_CONFIGS = {
        "rag_ingestion_single": {
            "payload": {"source_path": "s3://office-test/03_Die Verfassung der Allmende.pptx"},
            "overrides": {"StoreQdrant": {"collection_name": "test4"}}
        },
        
        "rag_ingestion_streaming": {
            "payload": {"s3_bucket": "office-test"},
            "overrides": {}
        }, 
        
        "rag_request": {
            "payload": {
                "prompt_query": "What is known about attention in LLMs?",
                "prompt_llm":
                    ("Answer the following question only based on the literature in the prompt! "
                     "Don't use the knowledge in your training data! Answer only in markdown format. "
                     "Answer in short bullet points with references! Provide a bibliography"
                    )   
                },
            "overrides": {}
        }
    }

    # Hart codierte Pipeline-ID zur Auswahl
    pipeline_id = "rag_ingestion_streaming"

    # Werte aus dem Dictionary laden (mit sicherem Fallback via .get)
    config = PIPELINE_CONFIGS.get(pipeline_id, {})
    payload = config.get("payload", {})
    overrides = config.get("overrides", {})

    asyncio.run(
        test_api(
            pipeline_id=pipeline_id,
            payload=payload,
            overrides=overrides
        )
    )
