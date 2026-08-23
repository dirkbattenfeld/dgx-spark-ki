from typing import List, Any

from applications.rag.pipelines.rag_ingestion.steps.models import ChunkedDocument
from applications.rag.pipelines.extract.configs import ExtractConfig
from applications.rag.pipelines.extract.models import ExtractResult, ChunkExtraction 

from libs.streampipe.observability import trace_action

@trace_action(step_name="extract")
async def extract_action(chunked_doc: ChunkedDocument, vllm_client: Any, config: ExtractConfig) -> ExtractResult:
    """
    Iteriert über die parent_chunks des ChunkedDocument (bis zu config.max_chunks)
    und führt für jeden Chunk eine isolierte Extraktion via vLLM aus.
    """
    source_path = chunked_doc.source.json_path or "unknown_source"
    print(f"🔄 [Extract] Starte Extraktion für: {source_path}...")
    print(f"       Verarbeite maximal {config.max_chunks} von {len(chunked_doc.parent_chunks)} verfügbaren Parent-Chunks.")

    extractions: List[ChunkExtraction] = []
    total_p_tokens = 0
    total_c_tokens = 0
    model_name = getattr(vllm_client, "MODEL_LLM", "Qwen")
    
    # Nutze nur so viele Chunks wie in max_chunks konfiguriert
    chunks_to_process = chunked_doc.parent_chunks[:config.max_chunks]

    for i, p_chunk in enumerate(chunks_to_process, 1):
        meta = p_chunk.meta or {}
        page_list = meta.get("page_numbers", [])
        
        # Falls der Text zu lang für das Zeichenlimit ist, schneiden wir ihn sicherheitshalber ab
        text_context = p_chunk.text
        if len(text_context) > config.max_context_chars:
            print(f"⚠️ Chunk [{i}] überschreitet max_context_chars. Wird gekürzt.")
            text_context = text_context[:config.max_context_chars]

        # Zusammenbau des User-Prompts für diesen spezifischen Chunk
        user_msg = (
            f"{config.user_extraction_instruction}\n\n"
            f"--- START TEXTABSCHNITT (S. {page_list}) ---\n"
            f"{text_context}\n"
            f"--- ENDE TEXTABSCHNITT ---"
        )
        
        if config.no_think: 
            user_msg += " /no_think"

        print(f"   🚀 Sende Chunk {i}/{len(chunks_to_process)} (ID: {p_chunk.id[:8]}...) an LLM...")

        # Native vLLM chat_async aufrufen
        response = await vllm_client.chat_async(
            prompt=user_msg,
            system_prompt=config.system_prompt,
            max_tokens=config.max_tokens,
            temperature=config.temperature
        )
        
        raw_answer = response.get("text", "").strip()
        p_tokens = response.get("usage", {}).get("prompt_tokens", 0)
        c_tokens = response.get("usage", {}).get("completion_tokens", 0)
        
        if "model" in response:
            model_name = response["model"]

        # Akkumulieren der Tokens über den gesamten Run
        total_p_tokens += p_tokens
        total_c_tokens += c_tokens

        # Einzel-Extraktion wegsichern
        extractions.append(
            ChunkExtraction(
                parent_id=p_chunk.id,
                page_numbers=page_list,
                raw_llm_output=raw_answer,
                completion_tokens=c_tokens
            )
        )

    # Zusammenfassende Metriken für die Pipeline
    pipeline_metrics = {
        "total_prompt_tokens": total_p_tokens,
        "total_completion_tokens": total_c_tokens,
        "total_tokens_used": total_p_tokens + total_c_tokens,
        "chunks_processed": len(extractions),
        "status": "success" if extractions else "empty"
    }

    return ExtractResult(
        source_path=source_path,
        extractions=extractions,
        total_prompt_tokens=total_p_tokens,
        total_completion_tokens=total_c_tokens,
        model=model_name,
        status="success" if extractions else "empty",
        extras=pipeline_metrics
    )
