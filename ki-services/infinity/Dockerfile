FROM nvcr.io/nvidia/pytorch:25.03-py3
WORKDIR /app

# 1. Kern schützen
RUN pip freeze > constraints.txt

# 2. Schritt A: Die Infrastruktur (mit Checks, da unkritisch)
RUN pip install -c constraints.txt \
    "fastapi" "uvicorn[standard]" "orjson" "prometheus-fastapi-instrumentator" \
    "coloredlogs" "starlette<1.0.0" "annotated-doc>=0.0.2" "pydantic-settings"

# 2. Schritt B: Die ML-Bibliotheken (OHNE Abhängigkeitsprüfung)
# Hier erzwingen wir die Versionen, die wir im interaktiven Test validiert haben
RUN pip install --no-deps \
    "transformers==4.45.2" \
    "sentence-transformers>=3.0.1" \
    "optimum==1.22.0" \
    "huggingface-hub<0.26.0" "tokenizers<0.21,>=0.20"

# 3. App ohne neue Abhängigkeiten
RUN pip install --no-deps "infinity_emb[torch,server]==0.0.77"

# Wir lassen den ENTRYPOINT flexibel, damit Compose entscheiden kann
ENTRYPOINT ["/usr/local/bin/infinity_emb"]
