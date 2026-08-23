# rag_gui/core/ports.py (Strikte hexagonale Grenze)
from abc import ABC, abstractmethod
from typing import Callable, Dict, Any, Awaitable

class EventBusPort(ABC):
    @abstractmethod
    async def publish(self, topic: str, data: Dict[str, Any]) -> None:
        """Publiziert ein Event auf einem spezifischen Topic."""
        pass

    @abstractmethod
    def subscribe(self, pattern: str, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]) -> None:
        """
        Abonniert ein Pattern (z.B. 'user:dirk:*'). 
        Der Callback muss eine asynchrone Funktion sein, die das exakte Topic und die Daten nimmt.
        """
        pass
