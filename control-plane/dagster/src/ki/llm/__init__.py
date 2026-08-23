# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.18.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
# llm/__init__.py

# Importiere alle Klassen und Funktionen aus dem Modul llama.py
from .llama import LLM, LocalLlamaLLM, LlmConfig, clean_antwort_llm

# Definiere die öffentliche API des Packages
__all__ = [
    "LLM",              # Basisklasse für LLMs
    "LocalLlamaLLM",    # Hauptklasse für Nutzer
    "LlmConfig",        # Konfigurationsobjekt
    "clean_antwort_llm" # Hilfsfunktion
]

# %%
