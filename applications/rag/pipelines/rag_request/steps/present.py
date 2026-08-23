import logging
from rich.console import Console
from rich.markdown import Markdown
from typing import Any, Dict
from applications.rag.pipelines.rag_request.steps.configs import EmptyConfig
from applications.rag.pipelines.rag_request.steps.models import GenerationResult

logger = logging.getLogger("Pipeline.PresentResult")

async def present_action(result: GenerationResult, config: EmptyConfig) -> Dict[str, Any]:
    """
    Gibt die Frage und die generierte Antwort des LLMs optisch 
    ansprechend auf dem Bildschirm aus.
    """
    if not isinstance(result, GenerationResult):
        return {"status": "error", "error": "Ungültiges GenerationResult"}
    
    console = Console()
    md = Markdown(result.answer)

    # Schickes Terminal-UI Trennelement
    print("\n" + "Formatiertes Ergebnis".center(60, "-"))
    print(f"❓ Suche: {result.prompt_query}")
    print(f"❓ Prompt: {result.prompt_llm}")
    print("-" * 60)
    print(f"🤖 ANTWORT ({result.model}):\n")
    console.print(md)
    print("-" * 60)
    print(f"🪙  Tokens: Prompt {result.prompt_tokens} / Gen {result.completion_tokens}")
    print("=" * 60 + "\n")

    return {
        "status": "presented",
        "tokens_total": result.prompt_tokens + result.completion_tokens
    }