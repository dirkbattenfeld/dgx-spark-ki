# test_pipeline_factory.py
import asyncio
import logging
import json
from applications.rag.pipelines.config import ENABLED_PIPELINES
from libs.pipeline.registry import registry
from libs.observability import ChannelConfig, ObservabilityConfig, configure_observability
from libs.observability.helper import format_dict_tree

# Logging konfigurieren, damit man die Ausgaben sieht
logger = logging.getLogger("LocalTest")

async def main(pipeline_id: str, payload: dict, overrides: dict):
    logpath = "projects/miontec/log.json"
    
    # Observability konfigurieren
    obs_config = ObservabilityConfig(
        service_name="pipeline-factory-service",
        global_log_level="INFO",
        otlp_enabled=False,
        channels={
#            "trace": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "data": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "system": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
        }
    )
    configure_observability(obs_config)
    
    logger.info("=" * 60)
    logger.info("🧪 STARTE Dokumenten Ingestion")
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
        logger.info("✅ InGESTION ERFOLGREICH BEENDET!")
        logger.info("Ergebnis-Zusammenfassung: %s", format_dict_tree(result))
        logger.info("=" * 60)      
        with open(logpath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        logger.info("LogFile: %s",logpath)      
        
    except Exception as e:
        logger.exception("❌ Fehler bei der lokalen Ausführung: %s", e)


if __name__ == "__main__":
    # Dict mit Konfigurationen je Pipeline
    PIPELINE_CONFIGS = {
        "rag_ingestion_streaming": {
            "payload": {"s3_bucket": "miontec"},
            "overrides": {"StoreQdrant": {"collection_name": "test4"}}
        }
    }

    pipeline_id = "rag_ingestion_streaming"

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
