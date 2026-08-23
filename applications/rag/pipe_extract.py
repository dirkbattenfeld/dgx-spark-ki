import asyncio

# --- Imports aus der Request Pipeline Architektur ---
from applications.rag.pipelines.extract.configs import (
    ExportConfig,
    ExtractConfig,
    EmptyConfig,
    AggregateConfig
)

from applications.rag.pipelines.extract.environment import run_preparation

from applications.rag.pipelines.extract.models import AggregatedResult, ExtractResult
from applications.rag.pipelines.extract.steps.aggregate import aggregate_action, prep_extract_to_aggregation
from applications.rag.pipelines.extract.steps.loadchunks import loadchunks_action
from applications.rag.pipelines.extract.steps.extract import extract_action
from applications.rag.pipelines.extract.steps.export import export_excel_action


from applications.rag.pipelines.rag_ingestion.steps.models import (
    ExtractInput,
    ChunkedDocument
)

# --- Streampipe Core Komponenten ---
from libs.streampipe.runner import PipelineRunner
from libs.streampipe.step import PipelineStep
from libs.streampipe.statistics2log import statistics_from_log


# =====================================================================
# MAIN EXECUTION ENTRYPOINT 
# =====================================================================
async def main():
    # 1. Vorbereitungsphase außerhalb der Pipeline (Infrastruktur & Clients)
    env = run_preparation()
    
    print("\n" + "="*60)
    print("🚀 INITIALISIERE Extract STREAMING PIPELINE")
    print(f"   Dispatcher-Modus:         {getattr(env.config, 'USE_DISPATCHER', False)}")
    print(f"   Maximale Parallelität:     {getattr(env.config, 'MAX_CONCURRENT_DOCUMENTS', 10)}")
    print("="*60)
    
    # Konfigurationen für die einzelnen Request-Schritte instanziieren
    loadyaml_config = EmptyConfig()
    
    extract_config = ExtractConfig(
        max_tokens = 65536,
        temperature = 0.1,
        no_think = False,
        max_context_chars = 400000,
        max_chunks = 1000
    )
    
    aggregate_config = AggregateConfig(
        dedup_keys = ["jahr", "bezeichnung"]    
    )   
    
    export_config = ExportConfig(  
        target_extension = ".xlsx"
    )

    yaml_paths = env.scan_source_files()
    
    if not yaml_paths:
        print("❌ Keine yamls mit chunks zur Verarbeitung gefunden. Pipeline bricht ab.")
        return

    print(f"🎯 {len(yaml_paths)} S3-Dokumente mit .chunks.yaml für die Pipeline bereitgestellt.")
  
    # 2. Definition der Pipeline-Schritte (Modernisiert & Entkoppelt)
    # Keine partial-Ketten mehr: Die Zuweisung der Singletons regelt die Framework-Brücke!
    loadchunks_step = PipelineStep(
        name="loadchunks",
        input_class=ExtractInput,
        config=loadyaml_config,
        step_action=loadchunks_action
    )

    extract_step = PipelineStep(
        name="extract",
        input_class=ChunkedDocument,
        config=extract_config,
        step_action=extract_action
    )
    
    aggregate_step = PipelineStep(
        name="aggregate",
        input_class=ExtractResult,
        config=aggregate_config,
        step_action=aggregate_action,
        step_preparation=prep_extract_to_aggregation
    )
    
    export_step = PipelineStep(
        name="export",
        input_class=AggregatedResult,
        config=export_config,
        step_action=export_excel_action,
    )
            
    # 3. Pipeline-Infrastruktur aufbauen (Runner & Stats)
    pipeline_runner = PipelineRunner(
        steps=[loadchunks_step, extract_step, aggregate_step, export_step], 
        env=env,
        initial_input_class=ExtractInput,
        input_field_name="source_path"        
    )

        # 4. Pipeline starten
    print("\n🎬 Starte paralleles Extract-Streaming...")
    await pipeline_runner.run(yaml_paths)

    # 5. Finale Statistikausgabe über die Request-Laufzeiten
    statistics_from_log(env.trace_config.filepath) 


if __name__ == "__main__":
    asyncio.run(main())