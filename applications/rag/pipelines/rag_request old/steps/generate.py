from typing import Any
from applications.rag.pipelines.rag_request.configs import GenerateConfig
from applications.rag.pipelines.rag_request.models import EnrichedResult, GenerationResult
from libs.streampipe.observability import trace_action


@trace_action(step_name="generate")
async def generate_action(
    input_data: EnrichedResult, 
    vllm_client: Any, 
    config: GenerateConfig
) -> GenerationResult:
    """
    Nutzt die native, spezialisierte chat_async-Methode des VLLMClients.
    Baut den Kontext basierend auf den EnrichedHits (Parent- oder Child-Texte) zusammen.
    """
    
    # Wird eine Antwort vom LLM erwartet?
    if not config.generate:
        return GenerationResult(
            prompt_query=input_data.prompt_query,
            prompt_llm=getattr(input_data, "prompt_llm", "") or "",
            answer="Keine Antwort vom LLM angefordert.",
            prompt="",
            prompt_tokens=0,
            completion_tokens=0,
            model="None",
            status="generate set to false",
            extras={}  
        )
    
    parts = []
    curr_chars = 0
    
    # Debug-Print um zu sehen, ob überhaupt Hits ankommen
    print(f" debug: generate_action empfing {len(input_data.hits)} Hits.")

    for i, hit in enumerate(input_data.hits, 1):
        # 1. Text-Extraktion: Priorität auf Parent-Text, Fallback auf Child-Text
        text = hit.parent_text or hit.rerank_hit.original_hit.text
        
        # 2. Sichere Metadaten-Extraktion aus dem tief verschachtelten SearchHit
        search_hit = hit.rerank_hit.original_hit
        meta = getattr(search_hit, "meta", {}) or {}
        
        # Sicherstellen, dass headings und page_numbers Listen/Werte sind (Fallback auf leere Strukturen)
        headings_list = meta.get("headings", []) if isinstance(meta, dict) else getattr(meta, "headings", [])
        page_list = meta.get("page_numbers", []) if isinstance(meta, dict) else getattr(meta, "page_numbers", [])
        
        # Header formatieren
        headings_str = " > ".join(headings_list) if headings_list else "Allgemein"
        pages_str = ", ".join(str(p) for p in page_list) if page_list else "?"
        
        header = f"[{i}] {headings_str} (S. {pages_str})"
        block = f"{header}\n{text}"
        
        # 3. Zeichenbegrenzung prüfen
        if curr_chars + len(block) < config.max_context_chars:
            parts.append(block)
            curr_chars += len(block)
        else:
            print(f"⚠️ Kontextlimit erreicht. Überspringe restliche Chunks.")
            break

    # 4. Zusammenbau der Nachricht
    context_joined = '\n\n---\n\n'.join(parts)
    
    # Visuelles Feedback im Terminal, ob der Kontext befüllt wurde
    if not context_joined.strip():
        print("❌ WARNUNG: Der generierte Kontext für das LLM ist LEER!")
    else:
        print(f"   Kontext erfolgreich befüllt ({len(parts)} Blöcke, {curr_chars} Zeichen).")

    prompt = getattr(input_data, "prompt_llm", "") or ""
    user_msg = f"Kontext:\n\n{context_joined}\n\nFrage: {prompt}"
    if config.no_think: 
        user_msg += " /no_think"

    # 🚀 SDK-Spezifischer vLLM-Aufruf
    response = await vllm_client.chat_async(
        prompt=user_msg,
        system_prompt=config.system_prompt,
        max_tokens=config.max_tokens,
        temperature=config.temperature
    )
    
    answer = response.get("text", "").strip()
    prompt_tokens = response.get("usage", {}).get("prompt_tokens", 0)
    completion_tokens = response.get("usage", {}).get("completion_tokens", 0)
    model_name = response.get("model", getattr(vllm_client, "MODEL_LLM", "Qwen"))

    pipeline_metrics = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "context_blocks_used": len(parts),
        "model": model_name,
        "status": "success"
    }

    return GenerationResult(
        prompt_query=input_data.prompt_query,
        prompt_llm=input_data.prompt_llm,
        answer=answer,
        prompt=user_msg,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model_name,
        status="success",
        extras=pipeline_metrics  
    )
