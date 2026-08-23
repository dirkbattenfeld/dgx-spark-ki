from rag_gui.core.orchestrator import Orchestrator
from typing import Dict, Any

class ChainlitPresenter:
    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator
        self.orchestrator.register_ui_listener(
            pattern="user:*", 
            callback=self._log_event_to_console
        )
        self._session_settings: Dict[str, Dict[str, Any]] = {}
        
    def update_session_settings(self, session_id: str, settings: Dict[str, Any]):
        if session_id not in self._session_settings:
            self._session_settings[session_id] = {}
        self._session_settings[session_id].update(settings)

    def get_session_settings(self, session_id: str) -> Dict[str, Any]:
        return self._session_settings.get(session_id, {
            "collection_name": "alanus-pptx",
            "limit": 100,
            "score_threshold": 0.60,
            "top_n": 5,
            "temperature": 0.2,
            "max_tokens": 1024
        })
        
    async def _log_event_to_console(self, topic: str, data: dict):
        """Dieser Callback wird vom MemoryEventBus asynchron gefeuert."""
        print(f"\n📢 [EVENT-BUS-TEST] Topic: {topic}")
        print(f"📦 [EVENT-BUS-TEST] Payload: {data}\n")

    async def handle_rag_query(self, text: str, session_id: str, user_id: str) -> dict:
        settings = self.get_session_settings(session_id)
        return await self.orchestrator.process_turn(text, session_id, user_id, mode="rag", settings=settings)
    
    async def handle_basket_compute(self, text: str, session_id: str, user_id: str) -> dict:
        settings = self.get_session_settings(session_id)
        return await self.orchestrator.process_turn(text, session_id, user_id, mode="basket", settings=settings)
    
    async def handle_plain_compute(self, text: str, session_id: str, user_id: str) -> dict:
        settings = self.get_session_settings(session_id)
        return await self.orchestrator.process_turn(text, session_id, user_id, mode="plain", settings=settings)
        
    async def toggle_chunk(self, user_id: str, chunk_id: str) -> bool:
        return await self.orchestrator.toggle_chunk_in_basket(user_id, chunk_id)

    async def get_basket(self, user_id: str) -> list:
        return await self.orchestrator.get_basket_ids(user_id)
    
    async def get_collections(self) -> list:
        return await self.orchestrator.get_available_collections()
    
