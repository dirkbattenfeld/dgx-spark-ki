# Python 3.12 bietet deutliche Performance-Vorteile im Bytecode-Handling auf ARM64
FROM python:3.12-slim

# System-Abhängigkeiten: Minimalistisch für Orchestration
RUN apt-get update && apt-get install -y \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. uv kopieren
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvbin/uv

# 2. Requirements kopieren
COPY requirements.txt .

# 3. Installation als ROOT ausführen (daher kein --chown beim COPY nötig)
# Wir setzen UV_LINK_MODE=copy, um die Warnung zu unterdrücken
RUN UV_LINK_MODE=copy /uvbin/uv pip install --system --no-cache-dir -r requirements.txt

# 4. Jetzt erst den User und die Verzeichnisse vorbereiten
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/dagster_home /app/src && \
    chown -R appuser:appuser /app

# 5. User wechseln für den sicheren Betrieb
USER appuser

ENV PYTHONPATH=/app/src
ENV DAGSTER_HOME=/app/dagster_home
