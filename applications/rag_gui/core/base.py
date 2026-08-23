# applications/rag_gui/base.py
from abc import ABC, abstractmethod
from typing import Optional, List

class StateRepository(ABC):
    @abstractmethod
    async def set_active_session(self, user_id: str, session_id: str) -> None: pass
    @abstractmethod
    async def get_active_session(self, user_id: str) -> Optional[str]: pass
    @abstractmethod
    async def add_turn(self, turn_id: str, session_id: str, user_query: str, llm_answer: str, chunk_ids: List[str]) -> None: pass
    @abstractmethod
    async def toggle_basket(self, user_id: str, chunk_id: str) -> bool: pass
    @abstractmethod
    async def get_basket(self, user_id: str) -> List[str]: pass
    @abstractmethod
    async def get_basket_chunk_texts(self, user_id: str) -> List[str]:
        """
        Holt die reinen Textinhalte aller Chunks, die sich aktuell 
        im Basket des Benutzers befinden.
        """
        pass
    