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
ENV HF_HOME=/app/.cache/huggingface
ENV PATH=/home/appuser/.local/bin:$PATH

# --------------------------
# Requirements installieren
# --------------------------
COPY --chown=appuser:appuser requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvbin/uv
RUN /uvbin/uv pip install --system --no-cache-dir -r requirements.txt

#RUN pip install uv && \
#    uv pip install --system --no-cache-dir -r requirements.txt

# --------------------------
# Editable Package vorbereiten
# --------------------------
# Kopiere nur pyproject.toml, nicht src (wird gemountet)
COPY --chown=appuser:appuser pyproject.toml ./

# --------------------------
# Userwechsel
# --------------------------
USER appuser


