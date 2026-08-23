# --------------------------
# Basis-Image
# --------------------------
FROM python:3.11-slim

# --------------------------
# System-Abhängigkeiten
# --------------------------
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# --------------------------
# User anlegen (nicht root)
# --------------------------
ARG UID=1000
ARG GID=1000
RUN groupadd -g $GID appuser \
    && useradd -m -u $UID -g $GID appuser

# --------------------------
# Arbeitsverzeichnis
# --------------------------
WORKDIR /app

# --------------------------
# Environment Variablen
# --------------------------
ENV PYTHONPATH=/app/src
ENV PATH=/home/appuser/.local/bin:$PATH
# HF_HOME wird erst im KI-Image gesetzt

# --------------------------
# uv installieren
# --------------------------
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvbin/uv

# --------------------------
# Requirements installieren
# --------------------------
COPY --chown=appuser:appuser requirements.txt .
RUN /uvbin/uv pip install --system --no-cache-dir -r requirements.txt

# --------------------------
# Editable Package vorbereiten
# Kopiere nur pyproject.toml, src wird gemountet
# --------------------------
COPY --chown=appuser:appuser pyproject.toml ./

# --------------------------
# Userwechsel
# --------------------------
USER appuser
