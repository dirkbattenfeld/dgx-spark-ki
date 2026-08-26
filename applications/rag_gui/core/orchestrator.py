# apps/rag_chainlit/orchestrator.py
import uuid
import textwrap
from typing import List, Dict, Any, Optional, Callable, Awaitable
from rag_gui.core.ports import EventBusPort  
from rag_gui.core.models import RetrievalChunk
from rag_gui.core.queryhandler import TemplateManager, QueryParser, PromptRewriter, PromptBuilder

class Orchestrator:
    def __init__(self, state_repository, client, event_bus: EventBusPort):
        self.state_db = state_repository
        self.sdk = client
        self.event_bus = event_bus
        self.vllm_client = self.sdk.get_client("vllm")
        self.rag_request_client = self.sdk.get_client("rag_pipeline_service")
        self.qdrant_client = self.sdk.get_client("qdrant")
        self.chunk_cache: Dict[str, str] = {}
        # queryhandling
        self.template_manager = TemplateManager()
        self.parser = QueryParser()
        self.rewriter = PromptRewriter(vllm_client=self.vllm_client)
        self.builder = PromptBuilder()
    
    
    async def process_turn(
        self,
        user_query: str,
        session_id: str,
        user_id: str,
        mode: str = "plain", 
        settings: Optional[Dict[str, Any]] = None
    ) -> dict:
        
        # Anfrage an Hilfefunktion abfangen
        if user_query.strip().lower() in ["/help", "/hilfe"]:
            answer = textwrap.dedent("""
                📖 **System-Hilfe & Verfügbare Tags**
                            
                **Modus "RAG Retrieval":**
                <search>Suchanfrage für die Vektordatenbank bitte mit Suchbegriffen ohne Sonderzeichen formulieren.</search>
                
                <instruction>Auftrag für das Large Language Model (LLM) als qualifizierten Prompt formulieren.</instruction>
                
                Das LLM antwortet ausschließlich auf Basis der gefundenen Chunks, die im RAG Cockpit inspiziert werden können.
                Mit dem Warenkorb Symbol kann ein Chunk im Dokumentenkorb gespeichert werden.
                            
                **Modus "LLM auf Chunks im Dokumentenkorb":**
                Das LLM antwortet ausschließlich auf Basis der Chunks im Dokumentenkorb und nutzt kein Wissen aus seinen Trainingsdaten.
                            
                **Modus "LLM (ohne Kontext)":**
                Das LLM antwortet ausschließlich auf Basis seiner Trainingsdaten.
                            
                /help oder /hilfe: Diese Hilfeseite.
            """)
            
            answer2 = """📖 System-Hilfe & Verfügbare Tags
            
            Modus "RAG Retrieval":
            <search>Suchanfrage für die Vektordatenbank bitte mit Suchbegriffen ohne Sonderzeichen formulieren.</search>
            <instruction>Auftrag für das Large Language Model (LLM) als qualifizierten Prompt formulieren.</instruction>"
            Das LLM antwortet ausschließlich auf Basis der gefundenen Chunks, die im RAG Cockpit inspiziert werden können.
            Mit dem Warenkorb Symbol kann ein Chunk im Dokumentenkorb gespeichert werden.
            
            Modus "LLM auf Chunks im Dokumentenkorb":
            Das LLM antwortet ausschließlich auf Basis der Chunks im Dokumentenkorb und nutzt kein Wissen aus seinen Trainingsdaten.
            
            Modus "LLM (ohne Kontext):
            Das LLM antwortet ausschließlich auf Basis seiner Trainingsdaten.
            
            /help oder /hilfe: Diese Hilfeseite.
            """
            prompt_query = "N/A (Help Command)"
            prompt_llm = "N/A (Help Command)"
            raw_chunks = []
            
            # Wir brauchen noch dummy chat_settings für den DB-Eintrag weiter unten
            settings_dict = settings or {}
            final_settings = self.template_manager.get_settings("default", settings_dict)

        else:       
            settings_dict = settings or {}
            
            # Parsing & Template Erkennung
            parsed_ctx = self.parser.parse(user_query)
            # Settings initialisieren (aus Verzeichnis oder Übergabe)
            chat_settings = self.template_manager.get_settings(parsed_ctx.active_template, settings_dict)
            # Verlauf holen (Dummy-Übergabe für späteren Rewriter)
            chat_history = [] # Hier später: await self.state_db.get_history(session_id)
            parsed_ctx = await self.rewriter.rewrite(parsed_ctx, chat_history, mode=mode)
            # Prompt Mapping für Suche und LLM-Aufruf
            prompt_query, prompt_llm, final_settings = self.builder.build(parsed_ctx, chat_settings, mode=mode)
            
            
            # Für maximale Entkopplung: Ermittle alle erlaubten Argumente der API-Methode
            # api_method = self.rag_request_client.call_async
            # allowed_args = inspect.signature(api_method).parameters
            # full_payload = final_settings.model_dump()
            # api_payload = {k: v for k, v in full_payload.items() if k in allowed_args}

            api_payload = final_settings.model_dump(
                exclude={"display_chunks"} 
            )
            
            if mode == "rag":
                response = await self.rag_request_client.call_async(
                    endpoint_name="rag_request",
                    pipeline_id="rag_request",
                    prompt_query=prompt_query,
                    prompt_llm=prompt_llm,
                    **api_payload    
                )
                
                raw_chunks = response.get("chunks", [])

                default_answer = "Dokumentensuche ohne Generierung einer Antwort."
                answer = response.get("answer", default_answer).strip() if final_settings.generate else default_answer
                
                # chunks parsen:
                parsed_chunks = [
                    RetrievalChunk.from_enriched_hit(chunk, idx) 
                    for idx, chunk in enumerate(raw_chunks)
                ]
                
            elif mode =="basket":           
                #user-query anreichern um die chunks aus dem Basket
                final_prompt = await self.enrich_prompt_with_basket(prompt_llm, user_id)
                
                response = await self.vllm_client.chat_async(
                    prompt=final_prompt,
                    system_prompt=("Du bist ein wissenschaftlicher Analyst. Beantworte Fragen ausschließlich auf Basis des bereitgestellten Kontexts." 
                                "Wenn im Kontext keine Informationen zur Frage enthalten sind, dann antworte mit 'KEINE INFORMATIONEN IM KONTEXT!'." 
                                "Erstelle am Ende Deiner Antwort eine Bibliographie und zitiere in Deiner Antwort sorgfältig! Antworte in Markdown."
                                "If you use mathematical formulas, always wrap them in $$ with a blank line before and after the formula block."),
                    max_tokens=final_settings.max_tokens,
                    temperature=final_settings.temperature,
                    no_think=final_settings.no_think   
                )
                answer = response.get("text", "").strip()
                parsed_chunks = []
                raw_chunks = []
            
            else:
                response = await self.vllm_client.chat_async(
                    prompt=prompt_llm,
                    system_prompt=("Du bist ein wissenschaftlicher Analyst. Antworte in Markdown. If you use mathematical formulas, always wrap them in $$ with a blank line before and after the formula block."),
                    max_tokens=final_settings.max_tokens,
                    temperature=final_settings.temperature,
                    no_think=final_settings.no_think   
                )
                answer = response.get("text", "").strip()
                parsed_chunks = [] 
                raw_chunks = []
             
        parsed_chunks = self._parse_chunks_to_pydantic(raw_chunks)
             
        turn_id = str(uuid.uuid4())
        await self.state_db.set_active_session(user_id, session_id)
        
        # Speichern: Wir konvertieren die Pydantic-Objekte direkt in Dicts für SQLite
        chunks_to_db = [chunk.model_dump() for chunk in parsed_chunks]
        await self.state_db.add_turn(
            turn_id=turn_id, 
            session_id=session_id, 
            user_query=user_query, 
            prompt_query=prompt_query,
            prompt_llm=prompt_llm,
            chat_settings=final_settings.model_dump(),
            llm_answer=answer, 
            chunks_data=chunks_to_db
        )

        # Event abfeuern
        await self.event_bus.publish(
            f"user:{user_id}:session:turn_completed", 
            {"session_id": session_id, "turn_id": turn_id}
        )
        
        return {"answer": answer, "chunks": parsed_chunks}
        

    def _parse_chunks_to_pydantic(self, raw_chunks: List[Any]) -> List[RetrievalChunk]:
        """
        Einheitliche Konvertierung: Wandelt rohe API-Daten oder DB-JSON-Einträge
        zuverlässig in eine Liste von RetrievalChunk-Pydantic-Objekten um.
        """
        if not raw_chunks:
            return []
            
        parsed = []
        for idx, chunk in enumerate(raw_chunks):
            if isinstance(chunk, dict):
                # Falls es aus der RAG-Schnittstelle kommt (verschachtelte Hits)
                if "rerank_hit" in chunk or "original_hit" in chunk:
                    parsed.append(RetrievalChunk.from_enriched_hit(chunk, idx))
                else:
                    # Falls es flach aus der DB kommt (bereits geparst abgespeichert)
                    parsed.append(RetrievalChunk(**chunk))
            elif isinstance(chunk, RetrievalChunk):
                parsed.append(chunk)
        return parsed
    
    
    async def toggle_chunk_in_basket(self, user_id: str, chunk_id: str) -> bool:
        is_in_basket = await self.state_db.toggle_basket(user_id, chunk_id)
        
        # Neu: Stats gleich berechnen und mitfeuern
        stats = await self.get_basket_stats(user_id)
        
        await self.event_bus.publish(
            f"user:{user_id}:basket:updated", 
            {
                "chunk_id": chunk_id, 
                "is_in_basket": is_in_basket,
                "stats": stats  
            }
        )
        return is_in_basket
            
    
    async def clear_whole_basket(self, user_id: str) -> None:
        """
        Löscht alle Chunks aus dem Basket des Benutzers in der Datenbank
        und benachrichtigt das System über den Event-Bus.
        """
        # 1. In der DB leeren (Wir gehen davon aus, dass state_db diese Methode anbietet)
        await self.state_db.clear_basket(user_id)
        
        # 2. Event an alle Listener feuern, dass der Korb geleert wurde
        await self.event_bus.publish(
            f"user:{user_id}:basket:updated", 
            {"chunk_id": "ALL", "is_in_basket": False}
        )
        print(f"🗑️ Basket für User {user_id} vollständig geleert.")
        

    async def get_basket_stats(self, user_id: str) -> Dict[str, int]:
        """
        Berechnet die Gesamtlänge der Chunks im Basket in Zeichen 
        sowie eine geschätzte Token-Anzahl (~4 Zeichen pro Token).
        """
        basket_texts = await self.state_db.get_basket_chunk_texts(user_id)

        if not basket_texts:
            return {"total_chars": 0, "estimated_tokens": 0}

        total_chars = 0
        for item in basket_texts:
            if isinstance(item, str):
                total_chars += len(item)
            elif isinstance(item, dict):
                # Fallback falls die DB Dicts/JSON liefert
                text = item.get("text") or item.get("content") or str(item)
                total_chars += len(text)
            else:
                total_chars += len(str(item))
        
        estimated_tokens = (total_chars + 3) // 4 if total_chars > 0 else 0

        return {
            "total_chars": total_chars,
            "estimated_tokens": estimated_tokens
        }
    
    
    async def set_user_active_session(self, user_id: str, session_id: str):
        await self.state_db.set_active_session(user_id, session_id)
        await self.event_bus.publish(
            f"user:{user_id}:session:changed", 
            {"session_id": session_id}
        )
    
    def register_ui_listener(self, pattern: str, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]):
        """
        Ermöglicht es Driving Adaptern (Presentern), sich anzumelden, 
        OHNE dass sie den zugrundeliegenden Infrastruktur-Bus direkt kennen müssen.
        """
        self.event_bus.subscribe(pattern, callback)
            
    async def get_basket_ids(self, user_id: str) -> List[str]:
        return await self.state_db.get_basket(user_id)

    async def get_active_session(self, user_id: str) -> Optional[str]:
        return await self.state_db.get_active_session(user_id)

    
    async def get_session_history_with_chunks(self, user_id: str) -> List[Dict[str, Any]]:
        session_id = await self.state_db.get_active_session(user_id)
        if not session_id:
            return []
            
        raw_turns = await self.state_db.get_turns_for_session(session_id)
        
        parsed_history = []
        for turn in raw_turns:
            raw_chunks = turn.get("chunks", [])
            # Identische Aufbereitung wie oben!
            parsed_chunks = self._parse_chunks_to_pydantic(raw_chunks)
            
            parsed_history.append({
                "user_query": turn.get("user_query", ""),
                "prompt_query": turn.get("prompt_query", ""),
                "prompt_llm": turn.get("prompt_llm", ""),
                "chat_settings": turn.get("chat_settings", {}),
                "answer": turn.get("answer", ""),
                "chunks": parsed_chunks
            })
            
        return parsed_history
    
    
    async def enrich_prompt_with_basket(self, user_query: str, user_id: str) -> str:
        """
        Holt alle Chunks aus dem Basket des Nutzers und reichert die 
        originale User-Query mit diesen als Kontext an.
        """
        # 1. Texte direkt und performant per SQL holen
        basket_texts = await self.state_db.get_basket_chunk_texts(user_id)
        
        if not basket_texts:
            return user_query  # Korb leer -> Query bleibt unverändert

        # 2. Texte für den Prompt formatieren
        formatted_segments = [
            f"--- [Dokumenten-Auszug {index}] ---\n{text.strip()}"
            for index, text in enumerate(basket_texts, start=1)
        ]

        context_block = "\n\n".join(formatted_segments)
        
        return (
            "Verwende ausschließlich den folgenden bereitgestellten Kontext aus dem Arbeitskorb (Basket), "
            "um die Frage des Nutzers am Ende zu beantworten.\n\n"
            "=== BEREITGESTELLTER KONTEXT ===\n"
            f"{context_block}\n"
            "================================\n\n"
            f"Frage des Nutzers:\n{user_query}"
        )
        
    async def get_available_collections(self) -> List[str]:
        """
        Fragt die tatsächlich in Qdrant existierenden Collections ab.
        Gibt eine Liste von Strings zurück.
        """
        try:
            # Da wir asynchron arbeiten:
            response = await self.qdrant_client.client.get_collections()
            
            # Qdrants Antwort-Objekt parsen (liefert eine Liste von CollectionDescription-Objekten)
            return [col.name for col in response.collections if not col.name.endswith("_parents")]
        except Exception as e:
            print(f"⚠️ Fehler beim Laden der Qdrant-Collections: {e}")
            # Stabiler Fallback, damit das UI nicht crasht
            return ["alanus-pptx", "ba25-paper", "ki-paper"]
