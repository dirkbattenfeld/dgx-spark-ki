# rag_gui/nicegui/presenter.py
import asyncio
from typing import Dict, Any, Callable
from nicegui import ui

class NiceGUICockpitPresenter:
    def __init__(self, orchestrator, user_id: str):
        self.orchestrator = orchestrator
        self.user_id = user_id
        self._render_callback: Callable[[], Any] = None
        
        # Sichere den Thread-Kontext für reaktive Push-Updates
        self.client = ui.context.client
        
        # Domain-Events abonnieren
        self.orchestrator.event_bus.subscribe(
            pattern=f"user:{user_id}:*",
            callback=self._handle_domain_event
        )

    def bind_render_trigger(self, render_callback: Callable[[], Any]):
        """Erlaubt der UI-Schicht, ihre Update-Funktion zu registrieren."""
        self._render_callback = render_callback
        # Initialen Render-Trigger abfeuern
        asyncio.create_task(self._trigger_ui_update())

    async def _handle_domain_event(self, topic: str, data: Dict[str, Any]):
        """Reagiert auf Backend-Events und stößt den UI-Refresh threadsafe an."""
        await self._trigger_ui_update()

    async def _trigger_ui_update(self):
        """Wechselt threadsafe in den Client-Scope und führt den UI-Render-Callback aus."""
        if not self._render_callback:
            return
        
        loop = asyncio.get_running_loop()
        def run_in_scope():
            try:
                with self.client:
                    loop.create_task(self._render_callback())
            except Exception as ex:
                print(f"❌ Fehler beim UI-Context-Wechsel: {ex}")
        
        loop.call_soon_threadsafe(run_in_scope)

    async def toggle_chunk(self, chunk_id: str):
        """Fachlicher Durchstich zum Ändern des Basket-Zustands."""
        await self.orchestrator.toggle_chunk_in_basket(self.user_id, chunk_id)

    async def clear_basket(self):
        """Fachlicher Durchstich zum Leeren des Baskets."""
        await self.orchestrator.clear_whole_basket(self.user_id)

    
    async def get_view_state(self) -> Dict[str, Any]:
        """Bereitet die puren Fachdaten framework-agnostisch für die Ansicht vor."""
        active_session = await self.orchestrator.get_active_session(self.user_id) or "Keine aktive Sitzung"
        basket_ids = await self.orchestrator.get_basket_ids(self.user_id)
        
        # Basket-Statistiken abrufen
        basket_stats = await self.orchestrator.get_basket_stats(self.user_id)
         
        # Holt die saubere Historie (bereits mit echten RetrievalChunk-Objekten)
        raw_history = await self.orchestrator.get_session_history_with_chunks(self.user_id)
        
        mapped_history = []
        
        # Sortierung der Turns: Neueste oben (reversed)
        for turn in reversed(raw_history):
            chunks = turn.get("chunks", [])
            
            # ÄNDERUNG: Sortierung absteigend nach Reranker Score (höchster Score zuerst)
            sorted_chunks = sorted(
                chunks, 
                key=lambda c: c.rerank_score, 
                reverse=True
            )
            
            mapped_history.append({
                "user_query": turn.get("user_query", ""),
                "prompt_query": turn.get("prompt_query", ""),
                "prompt_llm": turn.get("prompt_llm", ""),
                "chat_settings": turn.get("chat_settings", {}),
                "answer": turn.get("answer", ""),
                "chunks": sorted_chunks  # ÄNDERUNG: Direkte Übergabe der List[RetrievalChunk]
            })

        return {
            "active_session": active_session,
            "basket_ids": basket_ids,
            "basket_stats": basket_stats,
            "history_turns": mapped_history
        }
