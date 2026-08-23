# rag_gui/core/memory_bus.py (Austauschbarer Adapter)
import fnmatch
import asyncio
from typing import Callable, Dict, List, Any, Awaitable
from rag_gui.core.ports import EventBusPort

class PatternMatchingMemoryBus(EventBusPort):
    def __init__(self):
        # Wir speichern die Registrierungen als Liste von Tupeln: (Pattern, Callback)
        self._listeners: List[tuple[str, Callable[[str, Dict[str, Any]], Awaitable[None]]]] = []

    def subscribe(self, pattern: str, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]) -> None:
        self._listeners.append((pattern, callback))

    async def publish(self, topic: str, data: Dict[str, Any]) -> None:
        # Wir iterieren über alle angemeldeten Listener und prüfen das Pattern
        tasks = []
        for pattern, callback in self._listeners:
            if fnmatch.fnmatch(topic, pattern):
                # Erstellt eine asynchrone Task, damit ein hängender oder langsamer 
                # UI-Presenter niemals den Core-Prozess blockieren kann!
                tasks.append(asyncio.create_task(callback(topic, data)))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
