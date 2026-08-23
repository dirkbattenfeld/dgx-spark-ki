import re
import json
from typing import Optional, List, Dict, Any
from rag_gui.core.models import ChatSettings, ParsedContext


class TemplateManager:
    """Zuständig für das Laden von YAML-Templates. Aktuell Hardcoded-Fallback."""
    def get_settings(self, template_name: Optional[str], dict_settings: Dict[str, Any]) -> ChatSettings:
        # Hier später: YAML laden falls template_name existiert
        return ChatSettings(
            system_prompt=dict_settings.get("system_prompt", (
                "You are a scientific analyst. Answer questions only based on the provided context!. "
                "If the context contains no informations about the question, then answer: 'KEINE INFORMATIONEN IM KONTEXT!'. "
                "Cite the used sources from context in your answer preciseley and provide a bibliography! Answer in markdown."
                "If you use mathematical formulas, always wrap them in $$ with a blank line before and after the formula block."
            )),
            collection_name=dict_settings.get("collection_name", "alanus-pptx"),
            collection_name_parents=f"{dict_settings.get('collection_name', 'alanus-pptx')}_parents",
            limit=int(dict_settings.get("limit", 100)),
            score_threshold=float(dict_settings.get("score_threshold", 0.5)),
            top_n=int(dict_settings.get("top_n", 5)),
            max_tokens=int(dict_settings.get("max_tokens", 1024)),
            temperature=float(dict_settings.get("temperature", 0.2))
        )


class QueryParser:
    """Extrahiert XML-Tags und Slash-Commands sauber und sequentiell."""
    def parse(self, user_query: str) -> ParsedContext:
        # 1. Inhalte extrahieren
        search_queries = re.findall(r"<search>(.*?)</search>", user_query, re.DOTALL)
        instructions = re.findall(r"<instruction>(.*?)</instruction>", user_query, re.DOTALL)
        
        template_match = re.search(r"^/(\w+)", user_query.strip())
        active_template = template_match.group(1) if template_match else None
        
        # 2. Schrittweise JEDES Tag mitsamt Inhalt restlos ausradieren
        clean_query = user_query
        clean_query = re.sub(r"<search>.*?</search>", "", clean_query, flags=re.DOTALL)
        clean_query = re.sub(r"<instruction>.*?</instruction>", "", clean_query, flags=re.DOTALL)
        clean_query = re.sub(r"^/\w+", "", clean_query).strip()
            
        return ParsedContext(
            raw_query=user_query,
            clean_query=clean_query,
            search_queries=[q.strip() for q in search_queries if q.strip()],
            instructions=[i.strip() for i in instructions if i.strip()],
            active_template=active_template
        )
        

class PromptRewriter:
    def __init__(self, vllm_client):
        self.vllm_client = vllm_client

    async def rewrite(
        self,
        parsed_context: ParsedContext,
        chat_history: List[Dict],
        mode: str = "plain"
    )-> ParsedContext:
        
        # NUR optimieren, wenn der User keine expliziten Tags genutzt hat
        if mode == "rag" and parsed_context.raw_query and not parsed_context.search_queries and not parsed_context.instructions:
            
            print(f"[Rewriter Input] Raw Query erhalten: '{parsed_context.raw_query}'", flush=True)
            
            system_prompt = (
                "Du bist ein präziser Query-Deconstructor für ein RAG-System. "
                "Deine Aufgabe ist es, eine unstrukturierte User-Anfrage in zwei Teile zu zerlegen:\n"
                "1. search_query: Nur die harten Suchbegriffe/Entitäten für die Vektordatenbank (keine Füllwörter).\n"
                "2. clean_query: Der reine Arbeitsauftrag für das finale LLM.\n"
                "Antworte AUSSCHLIESSLICH im JSON-Format."
            )
            
            user_prompt = f"Zerlege diese Anfrage: {parsed_context.raw_query}"
            
            # Schneller, strukturierter LLM-Aufruf (JSON Mode)
            response = await self.vllm_client.chat_async(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.0,  # Absolut deterministisch
                response_format={"type": "json_object"}  # Falls von vllm unterstützt
            )
            
            raw_response_text = response.get("text", "{}")
            print(f"[Rewriter Output] Rohe vLLM-Antwort: {raw_response_text}", flush=True)
            
            try:
                data = json.loads(raw_response_text)
                
                # Kontext mit den KI-generierten Trennungen überschreiben
                parsed_context.clean_query = data.get("clean_query", parsed_context.clean_query)
                parsed_context.search_queries = [data.get("search_query", parsed_context.clean_query)]
                
                print(
                    f"[Rewriter Success] Match erfolgreich.\n"
                    f"  -> search_query (Qdrant): '{parsed_context.search_queries[0]}'\n"
                    f"  -> clean_query  (LLM):    '{parsed_context.clean_query}'",
                    flush=True
                )
                
            except json.JSONDecodeError:
                print(
                    f"[Rewriter Error] JSONDecodeError! vLLM hat kein gültiges JSON geliefert.\n"
                    f"  -> Text war: {raw_response_text}",
                    flush=True
                )
                # Robustes Fallback, falls das LLM mal fehlerhaftes JSON liefert
                pass
        else:
            if mode != "rag":
                print(f"[Rewriter Skipped]: mode = {mode}", flush=True)
            elif not parsed_context.raw_query:
                print("[Rewriter Skipped]: Keine User-Anfrage übergeben", flush=True)
            elif parsed_context.search_queries or parsed_context.instructions:
                print("[Rewriter Skipped]: User hat Suchanfrage mit XML Tags übergebn", flush=True)
        
        return parsed_context
    

class PromptBuilder:
    def build(
        self,
        parsed_context: ParsedContext,
        base_settings: ChatSettings,
        mode: str = "plain"
        ) -> tuple[str, str, ChatSettings]:
        
        if parsed_context.instructions:
            joined_instructions = "\n".join([f"- {i}" for i in parsed_context.instructions])
            prompt_llm = f"{parsed_context.clean_query}\n\nSpezifische Anweisungen:\n{joined_instructions}".strip()
        else:
            prompt_llm = parsed_context.clean_query

        if mode == "rag":
            prompt_query = parsed_context.search_queries[0] if parsed_context.search_queries else parsed_context.clean_query
        else:
            prompt_query = ""
        
        if not prompt_llm:
            base_settings.generate = False
        else:
            base_settings.generate = True

        return prompt_query, prompt_llm, base_settings
