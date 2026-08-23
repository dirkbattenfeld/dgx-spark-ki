import asyncio

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

from libs.streampipe.runner import PipelineRunner
from libs.streampipe.step import PipelineStep
from libs.streampipe.statistics2log import statistics_from_log

# =====================================================================
# MAIN EXECUTION ENTRYPOINT 
# =====================================================================
async def main():
    # 1. Vorbereitungsphase außerhalb der Pipeline (Globaler Build-Kontext)
    env = run_preparation()
     
    print("\n" + "="*60)
    print("🚀 INITIALISIERE STREAMING PIPELINE")
    print(f"   Dispatcher-Modus (Aktiv): {env.config.USE_DISPATCHER}")
    print(f"   Dokumenten-Parallelität:  {env.config.MAX_CONCURRENT_DOCUMENTS}")
    print("="*60)
    
    # Unsere Standard-Basiskonfigurationen
    extract_config = ExtractConfig(detailed_tables=True, ocr_enabled=True)
    chunk_config = ChunkConfig(child_max_tokens=512, max_child_chunks_per_parent=6, parent_overlap_chunks=1, merge_peers=True)                     # extract: child_max_tokens = 8000; max_childs_per_parent=6; parent_overlap_chunks=0
    contextualize_config = ContextualizeConfig(max_tokens=256, max_concurrent=32, temperature=0.1, document_window_chars=100000, no_think=True)
    embed_config = EmbedConfig(batch_size=64)
    store_config = StoreConfig(collection_name="alanus-pptx", vector_size=1024, distance="Cosine")  # <---

    pdf_paths = env.scan_source_files() #[:2]

    if not pdf_paths:
        print(f"❌ Keine Dateien ({env.config.S3_GLOB_PATTERN}) zur Verarbeitung gefunden. Pipeline bricht ab.")
        return

    print(f"🎯 {len(pdf_paths)} S3-Dokumente für die Pipeline bereitgestellt.")

    # 2. Definition der Pipeline-Schritte (Modernisiert & Entkoppelt)
    # Das Framework übernimmt die Zuweisung der passenden Singleton-Clients automatisch!
    extract_step = PipelineStep(
        name="Extract",
        input_class=ExtractInput, 
        config=extract_config,
        step_action=extract_action
    )
    
    chunk_step = PipelineStep(
        name="Chunk",
        input_class=RawDocument,  
        config=chunk_config,
        step_action=chunk_action
    )
    
    contextualize_step = PipelineStep(
        name="Contextualize",
        input_class=ChunkedDocument, 
        config=contextualize_config,
        step_action=contextualize_action
    )
    
    embed_step = PipelineStep(
        name="Embeddings",
        input_class=ChunkedDocument, 
        config=embed_config,
        step_action=embed_action
    )
    
    store_step = PipelineStep(
        name="StoreQdrant",
        input_class=EmbedOutput,  
        config=store_config,
        step_action=store_action
    )
        
    # 3. Pipeline-Infrastruktur aufbauen (Runner & Stats)
    pipeline_runner = PipelineRunner(
        steps=[extract_step, chunk_step, contextualize_step, embed_step, store_step], 
        env=env
    )

    # 4. Pipeline starten 
    print("\n🎬 Starte paralleles Dokumenten-Streaming...")
    await pipeline_runner.run(pdf_paths)
    
    # 5. Finale Statistikausgabe über die Request-Laufzeiten
    statistics_from_log(env.trace_config.filepath) 

if __name__ == "__main__":
    asyncio.run(main())
