#!/bin/bash
set -euo pipefail

# 1. PFADE & KONTEXT (Skript liegt im Projekt-Root: dgx-spark-stack)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Wir erzwingen hier den glasklaren, absoluten Pfad zur .env
ENV_ARG="--env-file $SCRIPT_DIR/.env"

# Unterverzeichnisse innerhalb von microservices
MICROSERVICES_DIR="$SCRIPT_DIR/microservices"
DISPATCHER_DIR="$MICROSERVICES_DIR/dispatcher"
GARAGE_DIR="$MICROSERVICES_DIR/garage-s3"
PIPELINE_SERVER_DIR="$MICROSERVICES_DIR/pipeline-server"
QDRANT_DIR="$MICROSERVICES_DIR/qdrant"
REDIS_DIR="$MICROSERVICES_DIR/redis"


# Pfad für die Logdy-PID-Datei und das Log-File
LOGDY_PID_FILE="$SCRIPT_DIR/.logdy.pid"
LOG_FILE="$SCRIPT_DIR/projects/streampipe_logs/rag_request_trace.jsonl"

# 2. HILFSFUNKTIONEN
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Hilfsfunktion für klickbare Links (kompatibel mit normalem Terminal & tmux)
log_link() {
    local label="$1"
    local url="$2"
    # Einfach als sauberer Plain Text – das Terminal verlinkt die URL von selbst
    log "${label} ${url}"
}

stop_all() {
    log "Fahre alle bekannten PC-Microservices herunter..."
    docker compose $ENV_ARG -f "$DISPATCHER_DIR/docker-compose.yaml" down || true
    docker compose $ENV_ARG -f "$GARAGE_DIR/docker-compose.yaml" down || true
    docker compose $ENV_ARG -f "$PIPELINE_SERVER_DIR/docker-compose.yaml" down || true
    docker compose $ENV_ARG -f "$QDRANT_DIR/docker-compose.yaml" down || true
    docker compose $ENV_ARG -f "$REDIS_DIR/docker-compose.yaml" down || true
    stop_logdy
}

stop_logdy() {
    if [ -f "$LOGDY_PID_FILE" ]; then
        local pid
        pid=$(cat "$LOGDY_PID_FILE")
        # Prüfen, ob der Prozess mit dieser PID überhaupt noch aktiv ist
        if kill -0 "$pid" 2>/dev/null; then
            log "Stoppe Logdy-Instanz (PID $pid)..."
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$LOGDY_PID_FILE"
    fi
}

# 3. PRÜFUNG DER ARGUMENTE
if [ $# -eq 0 ]; then
    echo "Fehler: Keine Microservices angegeben."
    echo "Usage: $0 {service1} {service2} ... oder $0 stop"
    echo "Mögliche Services: dispatcher, garage, pipeline-server, qdrant, redis, logdy"
    exit 1
fi

# Spezialfall: Globaler Stopp zuerst prüfen
if [ "$1" = "stop" ]; then
    log "Stoppe alle PC-Microservices..."
    stop_all
    log "Alle PC-Services vollständig gestoppt."
    exit 0
fi

# 4. DYNAMISCHE STEUERUNG (Abarbeitung aller Argumente)
for service in "$@"; do
    case "$service" in
        "dispatcher")
            log "Starte Dispatcher Service ..."
            docker compose $ENV_ARG -f "$DISPATCHER_DIR/docker-compose.yaml" up -d
            log "Monitor im terminal unter: nc localhost 9999"
            ;;
        "garage")
            log "Starte Garage S3 Service ..."
            docker compose $ENV_ARG -f "$GARAGE_DIR/docker-compose.yaml" up -d
            log_link "Garage Dashboard unter: " "http://localhost:4080"
            log_link "Garage webui unter: " "http://localhost:3909"
            ;;
        "pipeline-server")
            log "Starte Pipeline-Server ..."
            docker compose $ENV_ARG -f "$PIPELINE_SERVER_DIR/docker-compose.yaml" up -d
            ;;
        "qdrant")
            log "Starte Qdrant Vector Database ..."
            docker compose $ENV_ARG -f "$QDRANT_DIR/docker-compose.yaml" up -d
            log_link "Qdrant Web-Dashboard unter:" "http://localhost:6333/dashboard"
            ;;
        "redis")
            log "Starte Redis Database ..."
            docker compose $ENV_ARG -f "$REDIS_DIR/docker-compose.yaml" up -d
            log_link "RedisInsight Dashboard unter:" "http://localhost:5540"
            ;;
        "logdy")
            # Prüfen, ob Logdy bereits läuft
            if [ -f "$LOGDY_PID_FILE" ] && kill -0 "$(cat "$LOGDY_PID_FILE")" 2>/dev/null; then
                log "Logdy läuft bereits (PID $(cat "$LOGDY_PID_FILE"))."
            else
                log "Starte Logdy Web-UI für: $LOG_FILE ..."
                # Verzeichnis und Logdatei vorbereiten falls nicht vorhanden
                mkdir -p "$(dirname "$LOG_FILE")"
                touch "$LOG_FILE"

                # Nativer Hintergrund-Start entkoppelt vom aktuellen Terminal-Fenster
                logdy follow "$LOG_FILE" > /dev/null 2>&1 &
                echo $! > "$LOGDY_PID_FILE"

                log_link "Logdy Live-Dashboard geöffnet unter:" "http://localhost:8080"
            fi
            ;;
        *)
            log "WARNUNG: Unbekannter Service '$service' wird übersprungen."
            ;;
    esac
done
