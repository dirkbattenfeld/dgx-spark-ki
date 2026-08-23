# applications/rag/pipe_ingestion.py

import asyncio
import logging

from applications.rag.pipelines.rag_ingestion.pipeline import RagIngestionPipeline
from applications.rag.pipelines.rag_ingestion.config import RagIngestionConfig
from libs.pipeline.factory import PipelineRunnerFactory
from libs.observability import ChannelConfig, ObservabilityConfig, configure_observability

logger = logging.getLogger(__name__)

async def main():
    # Observability konfigurieren
    obs_config = ObservabilityConfig(
        service_name="rag-ingestion-service",
        global_log_level="INFO",
        otlp_enabled=False,
        channels={
            "trace": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "data": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "system": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
        }
    )
    configure_observability(obs_config)
    
    # Konfiguration definieren 
    config = RagIngestionConfig()
    
    # Pipeline-Manifest instanziieren
    pipeline_def = RagIngestionPipeline()

    # Factory baut den Runner (Environment & Steps intern gekapselt)
    runner = PipelineRunnerFactory.create_from_pipeline(
        pipeline=pipeline_def, 
        config=config, 
        mode="single"
    )

    logger.info("=" * 60)
    logger.info("🚀 INITIALISIERE STREAMING PIPELINE: %s", pipeline_def.pipeline_id)
    logger.info("   Dispatcher-Modus: %s", config.env.use_dispatcher)
    logger.info("   Parallelität:     %s", config.env.max_concurrent_documents)
    logger.info("=" * 60)

    # 4. Quell-Dateien über das im Runner gekapselte Environment scannen
    pdf_paths = runner.env.scan_source_files()
    if not pdf_paths:
        logger.error("❌ Keine Dateien (%s) zur Verarbeitung gefunden. Abbruch.", config.env.s3_glob_pattern)
        return
    
    initial_payloads = [{"source_path": path} for path in pdf_paths]
    logger.info("🎯 %d Dokumente für die Pipeline bereitgestellt.", len(initial_payloads))
        
    # 5. Pipeline mit Payloads ausführen
    logger.info("\n🎬 Starte paralleles Dokumenten-Streaming...")
    results = await runner.run(initial_payloads=initial_payloads)

    logger.info("✅ Processing beendet. %d Dokument-Ergebnisse empfangen.", len(results))

if __name__ == "__main__":
    asyncio.run(main())
