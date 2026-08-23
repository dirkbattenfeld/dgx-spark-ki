# applications/rag/pipe_request.py

import asyncio
import logging 

from applications.rag.pipelines.rag_request.pipeline import RagRequestPipeline
from applications.rag.pipelines.rag_request.config import RagRequestConfig
from libs.pipeline.factory import PipelineRunnerFactory
from libs.observability import ChannelConfig, ObservabilityConfig, configure_observability

logger = logging.getLogger(__name__)

async def main():
    # Observability konfigurieren
    obs_config = ObservabilityConfig(
        service_name="rag-request-service",
        global_log_level="INFO",
        otlp_enabled=False,
        channels={
            "trace": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "data": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "system": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
        }
    )
    configure_observability(obs_config)
    
    # Konfiguration definieren (Single Source of Truth)
    config = RagRequestConfig()

    # Pipeline-Manifest instanziieren
    pipeline_def = RagRequestPipeline()

    # Factory baut den Runner 
    runner = PipelineRunnerFactory.create_from_pipeline(
        pipeline=pipeline_def, 
        config=config, 
        mode="single"
    ) 
    
    logger.info("=" * 60)
    logger.info("🚀 INITIALISIERE SINGLE PIPELINE: %s", pipeline_def.pipeline_id)
    logger.info("   Dispatcher-Modus: %s", config.env.use_dispatcher)
    logger.info("   Parallelität:     %s", config.env.max_concurrency)
    logger.info("=" * 60)
    
    queries = [{"prompt_query": "What is known about the use of attention in the context of llms.",
                "prompt_llm":
        ("Answer the following question only based on the literature in the prompt! "
         "Don't use the knowledge in your training data! Answer only in markdown format. "
         
         "Answer in short bullet points with references! Provide a bibliography"
        )
    }       
    ]

    logger.info(f"🎯 {len(queries)} Queries für das parallele Processing bereitgestellt.")

    # 4. Pipeline starten
    logger.info("\n🎬 Starte paralleles Query-Streaming...")
    results = await runner.run(initial_payloads=queries)
    
    logger.info("=" * 60)
    print("DEBUG (result):", results)
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())