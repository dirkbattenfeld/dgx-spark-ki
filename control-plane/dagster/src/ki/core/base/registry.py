# registry.py

from typing import Dict, Type

class Registry:
    def __init__(self):
        self._registry: dict[str, type] = {}
    
    def register(self, key: str):
        def decorator(cls):
            self._registry[key] = cls
            return cls
        return decorator

    def get(self, key: str) -> type:
        if key not in self._registry:
            raise KeyError(f"Key '{key}' not registered")
        return self._registry[key]

    def contains(self, key: str) -> bool:
        return key in self._registry
