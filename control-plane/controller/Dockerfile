# Basis-Image
FROM python:3.11-slim

# System-Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ssh \
    openssh-client \
    ca-certificates \
    && curl -fsSL https://get.docker.com | sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements zuerst kopieren (bessere Cache-Nutzung)
COPY control-plane/controller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# PYTHONPATH setzen
ENV PYTHONPATH=/app/src:/app:/libs

EXPOSE 8501 8888

