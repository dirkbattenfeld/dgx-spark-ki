import asyncio

# --- Imports aus der Request Pipeline Architektur ---
from applications.rag.pipelines.rag_request.configs import (
    EmbedQueryConfig,
    SearchQdrantConfig,
    RerankConfig,
    ParentDocConfig,
    GenerateConfig,
    EmptyConfig
)
from applications.rag.pipelines.rag_request.models import (
    QueryInput,
    EmbeddedQuery,
    SearchResult,
    RerankResult,
    EnrichedResult,
    GenerationResult
)
from applications.rag.pipelines.rag_request.environment import run_preparation

from applications.rag.pipelines.rag_request.steps.embed import embed_action
from applications.rag.pipelines.rag_request.steps.search import search_action
from applications.rag.pipelines.rag_request.steps.rerank import rerank_action
from applications.rag.pipelines.rag_request.steps.fetch_parents import fetch_parents_action
from applications.rag.pipelines.rag_request.steps.generate import generate_action
from applications.rag.pipelines.rag_request.steps.present import present_action

# --- Streampipe Core Komponenten ---
from applications.rag.pipelines.rag_request.yaml.preparations import generate_prep, rerank_prep, search_prep
from libs.streampipe.runner import PipelineRunner
from libs.streampipe.step import PipelineStep
from libs.streampipe.statistics2log import statistics_from_log
import yaml

async def main():
    env = run_preparation()
    
    # =====================================================================
    # 1. YAML AUFTRÄGE EINLESEN & PAYLOADS BAUEN
    # =====================================================================
    yaml_path = "applications/rag/pipelines/rag_request/yaml/jobs.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
    
    # Jeder Job im YAML wird zu einem global_payload-Eintrag für die Pipeline
    jobs = config_data.get("jobs", [])
    
    if not jobs:
        print("❌ Keine Aufträge in der YAML gefunden.")
        return

    print("\n" + "="*60)
    print("🚀 INITIALISIERE DYNAMISCHE REQUEST STREAMING PIPELINE")
    print(f"   Geladene Aufträge aus YAML: {len(jobs)}")
    print("="*60)
    
    # Standard-Basiskonfigurationen (greifen, wenn im YAML etwas fehlt)
    embed_config = EmbedQueryConfig()
    search_config = SearchQdrantConfig(collection_name="ki-paper", limit=10, score_threshold=0.5)
    rerank_config = RerankConfig(top_n=5)
    parent_config = ParentDocConfig(collection_name="ki-paper_parents", fetch_parent=True)
    generate_config = GenerateConfig(temperature=0.1, max_tokens=500, no_think=True, max_context_chars=100000)

    # =====================================================================
    # 2. DEFINITION DER STEPS (Jetzt mit unseren Adaptern!)
    # =====================================================================
    embed_step = PipelineStep(
        name="EmbedQuery",
        input_class=QueryInput,
        config=embed_config,
        step_action=embed_action
    )
    
    search_step = PipelineStep(
        name="SearchQdrant",
        input_class=EmbeddedQuery,
        config=search_config,
        step_action=search_action,
        step_preparation=search_prep  
    )
    
    rerank_step = PipelineStep(
        name="RerankBGE",
        input_class=SearchResult,
        config=rerank_config,
        step_action=rerank_action,
        step_preparation=rerank_prep
    )  
    
    fetch_parents_step = PipelineStep(
        name="FetchParents",
        input_class=RerankResult,
        config=parent_config,
        step_action=fetch_parents_action
    )
    
    generate_step = PipelineStep(
        name="GenerateLLM",
        input_class=EnrichedResult,
        config=generate_config,
        step_action=generate_action,
        step_preparation=generate_prep  
    )
    
    present_step = PipelineStep(
        name="PresentTerminal",
        input_class=GenerationResult, 
        config=EmptyConfig(),  
        step_action=present_action
    )
        
    # 3. Pipeline-Infrastruktur aufbauen
    pipeline_runner = PipelineRunner(
        steps=[embed_step, search_step, rerank_step, fetch_parents_step, generate_step, present_step], 
        env=env,
        initial_input_class=QueryInput,
        input_field_name="query"  
    )

    # 4. Pipeline starten (Wir übergeben direkt die Liste der Dictionaries aus der YAML!)
    print("\n🎬 Starte paralleles Query-Auftrags-Streaming aus YAML...")
    await pipeline_runner.run(jobs)

    # 5. Finale Statistikausgabe
    statistics_from_log(env.trace_config.filepath) 

if __name__ == "__main__":
    asyncio.run(main())