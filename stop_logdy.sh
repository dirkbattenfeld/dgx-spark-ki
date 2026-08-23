#!/bin/bash
set -euo pipefail

# 1. PFADE & KONTEXT (Skript liegt im Projekt-Root: dgx-spark-stack)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Wir erzwingen hier den glasklaren, absoluten Pfad zur .env
ENV_ARG="--env-file $SCRIPT_DIR/.env"

# Pfad für die Logdy-PID-Datei und das Log-File
LOGDY_PID_FILE="$SCRIPT_DIR/.logdy.pid"
LOG_FILE="$SCRIPT_DIR/projects/streampipe_logs/rag.log"

# 2. HILFSFUNKTIONEN
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
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

stop_logdy
