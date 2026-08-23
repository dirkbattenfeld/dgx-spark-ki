# test_pipeline_factory.py
import asyncio
import logging
from applications.rag.pipelines.config import ENABLED_PIPELINES
from libs.pipeline.registry import registry
from libs.observability import ChannelConfig, ObservabilityConfig, configure_observability

# Logging konfigurieren, damit man die Ausgaben sieht
logger = logging.getLogger("LocalTest")

async def main(pipeline_id: str, payload: dict, overrides: dict):
    # Observability konfigurieren
    obs_config = ObservabilityConfig(
        service_name="pipeline-factory-service",
        global_log_level="INFO",
        otlp_enabled=False,
        channels={
            "trace": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "data": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "system": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
        }
    )
    configure_observability(obs_config)
    
    logger.info("=" * 60)
    logger.info("🧪 STARTE LOKALEN PIPELINE-TEST (OHNE API)")
    logger.info("=" * 60)

    # 1. Registry bootstrappen (genau wie in der FastAPI Bridge im Lifespan)
    registry.bootstrap(ENABLED_PIPELINES)

    # 2. Pipeline-ID abfragen
    logger.info("🔍 Hole Wrapper für Pipeline: '%s'", pipeline_id)

    try:
        wrapper = registry.get(pipeline_id)
    except KeyError:
        logger.error("❌ Pipeline '%s' nicht in Registry gefunden!", pipeline_id)
        return

    # 3. Pipeline lokal über den Wrapper ausführen 
    logger.info("🚀 Triggere Wrapper.execute()...")

    try:
        result = await wrapper.execute(incoming_payload=payload, overrides=overrides)
        logger.info("=" * 60)
        logger.info("✅ LOKALER TEST ERFOLGREICH BEENDET!")
        logger.info("Ergebnis-Zusammenfassung: %s", result)
        logger.info("=" * 60)
    except Exception as e:
        logger.exception("❌ Fehler bei der lokalen Ausführung: %s", e)


if __name__ == "__main__":
    # Dict mit Konfigurationen je Pipeline
    PIPELINE_CONFIGS = {
        "rag_ingestion_single": {
            "payload": {"source_path": "s3://office-test/03_Die Verfassung der Allmende.pptx"},
            "overrides": {"StoreQdrant": {"collection_name": "test4"}}
        },
        
        "rag_ingestion_streaming": {
            "payload": {"s3_bucket": "office-test"}
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

    pipeline_id = "rag_request"

    # Werte aus dem Dictionary laden (mit sicherem Fallback via .get)
    config = PIPELINE_CONFIGS.get(pipeline_id, {})
    payload = config.get("payload", {})
    overrides = config.get("overrides", {})
    
    asyncio.run(main(
        pipeline_id=pipeline_id,
        payload=payload,
        overrides=overrides
        )
    )
