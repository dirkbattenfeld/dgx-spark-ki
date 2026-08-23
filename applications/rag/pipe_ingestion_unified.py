import asyncio
import logging
from typing import List, Dict, Any

# =====================================================================
# 1. UNVERÄNDERTE IMPORTE (PROJEKT-PFADE)
# =====================================================================
from applications.rag.pipelines.rag_ingestion.steps.configs import (
    ChunkConfig,
    ContextualizeConfig,
    EmbedConfig,
    ExtractConfig,
    StoreConfig
)
from applications.rag.pipelines.rag_ingestion.steps.models import (
    ChunkedDocument,
    ExtractInput,
    RawDocument,
    EmbedOutput
)
from applications.rag.pipelines.rag_ingestion.environment import run_preparation

from applications.rag.pipelines.rag_ingestion.steps.chunk import chunk_action
from applications.rag.pipelines.rag_ingestion.steps.contextualize import contextualize_action
from applications.rag.pipelines.rag_ingestion.steps.embed import embed_action
from applications.rag.pipelines.rag_ingestion.steps.extract import extract_action
from applications.rag.pipelines.rag_ingestion.steps.store import store_action

# =====================================================================
# 2. FRAMEWORK IMPORTE (NEUE ARCHITEKTUR)
# =====================================================================
from libs.pipeline.factory import PipelineRunnerFactory
from libs.pipeline.step import PipelineStep
from libs.pipeline.statistics2log import statistics_from_log

logging.basicConfig(level=logging.ERROR)

NOISY_LOGGERS = ["httpx", "httpcore", "qdrant_client", "urllib3", "vllm", "infinity"]

for logger_name in NOISY_LOGGERS:
    logging.getLogger(logger_name).setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# =====================================================================
# 3. STRUKTURIERTE EINSTELLUNGEN (ZENTRALE USER CONFIG)
# =====================================================================
class PipelineStepConfigs:
    """
    Kapselt alle fachlichen Einstellungen für die einzelnen Steps an einem Ort,
    ohne sie in der Ausführungslogik zu verstreuen.
    """
    def __init__(
        self,
        extract: ExtractConfig = None,
        chunk: ChunkConfig = None,
        contextualize: ContextualizeConfig = None,
        embed: EmbedConfig = None,
        store: StoreConfig = None
    ):
        self.extract = extract or ExtractConfig(
            detailed_tables=True, 
            ocr_enabled=True
        )
        self.chunk = chunk or ChunkConfig(
            child_max_tokens=512, 
            max_child_chunks_per_parent=6, 
            parent_overlap_chunks=1, 
            merge_peers=True
        )
        self.contextualize = contextualize or ContextualizeConfig(
            max_tokens=256, 
            max_concurrent=32, 
            temperature=0.1, 
            document_window_chars=40000, 
            no_think=True
        )
        self.embed = embed or EmbedConfig(
            batch_size=64
        )
        self.store = store or StoreConfig(
            collection_name="test2", 
            vector_size=1024, 
            distance="Cosine"
        )


# =====================================================================
# 4. PIPELINE BUILDER (SEPARATION OF CONCERNS)
# =====================================================================
def build_rag_ingestion_steps(configs: PipelineStepConfigs) -> List[PipelineStep]:
    """
    Erzeugt die entkoppelten PipelineSteps. 
    Kapselt die Zuordnung von Input-Klassen, Actions und Konfigurationen.
    """
    return [
        PipelineStep(
            name="Extract",
            input_class=ExtractInput,
            config=configs.extract,
            step_action=extract_action
        ),
        PipelineStep(
            name="Chunk",
            input_class=RawDocument,
            config=configs.chunk,
            step_action=chunk_action
        ),
        PipelineStep(
            name="Contextualize",
            input_class=ChunkedDocument,
            config=configs.contextualize,
            step_action=contextualize_action
        ),
        PipelineStep(
            name="Embeddings",
            input_class=ChunkedDocument,
            config=configs.embed,
            step_action=embed_action
        ),
        PipelineStep(
            name="StoreQdrant",
            input_class=EmbedOutput,
            config=configs.store,
            step_action=store_action
        )
    ]


# =====================================================================
# 5. KLAR STRUKTURIERTER MAIN ENTRYPOINT
# =====================================================================
async def main():
    # SCHRITT 1: Umgebung & Observability initialisieren
    env = run_preparation()
    
    logger.info("=" * 60)
    logger.info("🚀 INITIALISIERE STREAMING PIPELINE")
    logger.info("   Dispatcher-Modus (Aktiv): %s", env.config.USE_DISPATCHER)
    logger.info("   Dokumenten-Parallelität:  %s", env.config.MAX_CONCURRENT_DOCUMENTS)
    logger.info("=" * 60)

    # SCHRITT 2: Quell-Dateien scannen und in generische Payload-Dicts mappen
    pdf_paths = env.scan_source_files()
    if not pdf_paths:
        logger.error("❌ Keine Dateien (%s) zur Verarbeitung gefunden. Abbruch.", env.config.S3_GLOB_PATTERN)
        return

    initial_payloads = [{"source_path": path} for path in pdf_paths]
    logger.info("🎯 %d S3-Dokumente für die Pipeline bereitgestellt.", len(initial_payloads))

    # SCHRITT 3: Step-Konfigurationen definieren und Steps bauen
    step_configs = PipelineStepConfigs()
    steps = build_rag_ingestion_steps(step_configs)

    # SCHRITT 4: Runner über die Factory erzeugen
    pipeline_runner = PipelineRunnerFactory.create(
        mode="streaming",
        steps=steps,
        env=env,
        initial_input_class=ExtractInput
    )

    # SCHRITT 5: Pipeline ausführen & Ergebnisse entgegennehmen
    logger.info("\n🎬 Starte paralleles Dokumenten-Streaming...")
    results = await pipeline_runner.run(initial_payloads=initial_payloads)

    logger.info("✅ Processing beendet. %d Dokument-Ergebnisse empfangen.", len(results))

    # SCHRITT 6: Ausführungsstatistiken ausgeben
    statistics_from_log(env.trace_config.filepath)

if __name__ == "__main__":
    asyncio.run(main())
