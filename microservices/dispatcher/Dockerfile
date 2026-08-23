# Nutzen der offiziellen ARM64-kompatiblen Python-Version
FROM python:3.11-slim

# System-Abhängigkeiten für Netzwerk-Tools und Build-Essentials
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis im Container
WORKDIR /app

# Abhängigkeiten kopieren und installieren
# Wir nutzen --no-cache-dir, um das Image auf dem GX10 klein zu halten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Den Rest des Codes kopieren (wird im Dev-Modus durch Compose überschrieben)
COPY . .

# Port für den Dispatcher (Hausformat-API)
EXPOSE 8000


