# Basis-Image (Schlank und sicher)
FROM python:3.11-slim

# System-Abhängigkeiten auf das absolute Minimum reduziert (curl für Healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements zuerst kopieren für optimale Docker-Layer-Cachings
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Der Standardbefehl (wird via docker-compose überschrieben, dient als Fallback)
CMD ["uvicorn", "microservices.pipeline_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8011"]

