FROM python:3.11-slim

# Nur die absolut notwendigen System-Libs (z.B. für asyncpg / postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements zuerst kopieren für optimales Caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Den Quellcode kopieren
COPY . .

# PYTHONPATH für deine modulare Projektstruktur setzen
ENV PYTHONPATH=/app/src:/app:/libs





