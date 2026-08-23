#!/bin/bash
set -euo pipefail

# 1. PFADE & KONTEXT (Skript liegt im Projekt-Root: dgx-spark-stack)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Wir erzwingen hier den glasklaren, absoluten Pfad zur .env
ENV_ARG="--env-file $SCRIPT_DIR/.env"

# Unterverzeichnisse innerhalb von ki-services
KI_SERVICES_DIR="$SCRIPT_DIR/ki-services"
DIFFUSERS_DIR="$KI_SERVICES_DIR/diffusers"
VLLM_DIR="$KI_SERVICES_DIR/vllm"
DOCLING_DIR="$KI_SERVICES_DIR/docling"
INFINITY_DIR="$KI_SERVICES_DIR/infinity"

# 2. HILFSFUNKTIONEN
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

stop_all() {
    log "Fahre alle bekannten Monorepo-Services herunter..."

    # vLLM Instanzen
    for proj in qwen80_l qwen80_m qwen80_s my_coder qwen3_coder_l qwen3_coder_s mini_coder qwen3_8b; do
        docker compose $ENV_ARG -f "$VLLM_DIR/vllm_template.yaml" -p "$proj" down || true
    done

    # Standalone Services
    docker compose $ENV_ARG -f "$DIFFUSERS_DIR/diffusers_template.yaml" -p "flux1" down || true
    docker compose $ENV_ARG -f "$DIFFUSERS_DIR/diffusers_template.yaml" -p "flux2" down || true
    docker compose $ENV_ARG -f "$DOCLING_DIR/docker-compose.yaml" down || true
    docker compose $ENV_ARG -f "$INFINITY_DIR/docker-compose.yaml" down || true
}

# Hilfsfunktion für den vLLM-Start
start_vllm() {
    local p_name="$1" m_path="$2" mem_util="$3" max_len="$4"
    log "Starte vLLM ($p_name) ..."

    MODEL="$m_path" \
    GPU_MEMORY_UTIL="$mem_util" \
    MAX_MODEL_LEN="$max_len" \
    docker compose \
        $ENV_ARG \
        -f "$VLLM_DIR/vllm_template.yaml" \
        -p "$p_name" up -d
    # Gibt dem vllm Container Vorsprung beim Start um GPU Reservierung abzuschließen
    sleep 10
}

# Hilfsfunktion für Diffusers
start_diffusers() {
    local p_name="$1" module_name="$2" port_num="$3"
    log "Starte diffusers ($p_name mit $module_name auf Port $port_num) ..."

    DIFFUSERS_MODULE="$module_name" \
    DIFFUSERS_PORT="$port_num" \
    docker compose $ENV_ARG -f "$DIFFUSERS_DIR/diffusers_template.yaml" -p "$p_name" up -d
}

# 3. PRÜFUNG DER ARGUMENTE
if [ $# -eq 0 ]; then
    echo "Fehler: Keine Microservices angegeben."
    echo "Usage: $0 {service1} {service2} ... oder $0 stop"
    echo "Mögliche Services: qwen80_l, qwen80_m, qwen80_s, my_coder, qwen3_coder_l, qwen3_coder_s, mini_coder, qwen3_8b, flux1, flux2, docling, infinity"
    exit 1
fi

# Spezialfall: Globaler Stopp zuerst prüfen
if [ "$1" = "stop" ]; then
    log "Stoppe alle Microservices"
    stop_all
    log "System im Monorepo vollständig gestoppt."
    exit 0
fi

# 4. PHASEN-STEUERUNG (Garantiert die Startreihenfolge)

# Listen für die Aufteilung vorbereiten
VLLM_SERVICES=()
OTHER_SERVICES=()

# Argumente filtern und einsortieren
for service in "$@"; do
    case "$service" in
        qwen80_l|qwen80_m|qwen80_s|my_coder|qwen3_coder_l|qwen3_coder_s|mini_coder|qwen3_8b)
            VLLM_SERVICES+=("$service")
            ;;
        flux1|flux2|docling|infinity)
            OTHER_SERVICES+=("$service")
            ;;
        *)
            log "WARNUNG: Unbekannter Service '$service' wird ignoriert."
            ;;
    esac
done


# --- PHASE 1: vLLM Instanzen starten ---
for service in "${VLLM_SERVICES[@]:+"${VLLM_SERVICES[@]}"}"; do
    case "$service" in
        "qwen80_l")
            start_vllm "qwen80_l" "nvidia/Qwen3-Next-80B-A3B-Instruct-NVFP4" "0.85" 131072
            ;;
        "qwen80_m")
            start_vllm "qwen80_m" "nvidia/Qwen3-Next-80B-A3B-Instruct-NVFP4" "0.75" 65536
            ;;
        "qwen80_s")
            start_vllm "qwen80_s" "nvidia/Qwen3-Next-80B-A3B-Instruct-NVFP4" "0.6" 65536
            ;;
        "my_coder")
            start_vllm "my_coder" "/root/models/Qwen2.5-Coder-32B-NVFP4_v1" "0.9" 32768
            ;;
        "qwen3_coder_l")
            start_vllm "qwen3_coder_l" "RedHatAI/Qwen3-Coder-Next-NVFP4" "0.92" 131072
            ;;
        "qwen3_coder_s")
            start_vllm "qwen3_coder_s" "RedHatAI/Qwen3-Coder-Next-NVFP4" "0.6" 65536
            ;;
        "mini_coder")
            start_vllm "mini_coder" "Qwen/Qwen2.5-Coder-3B-Instruct" "0.2" 8192
            ;;
        "qwen3_8b")
            start_vllm "qwen3_8b" "RedHatAI/Qwen3-8B-NVFP4" "0.6" 40960
            ;;
    esac
done

# --- TIMING-SCHUTZ ---
# Wenn mindestens ein vLLM-Service gestartet wurde UND danach noch andere Services folgen,
# warten wir 10 Sekunden, damit vLLM NCCL und die GPU ungestört initialisieren kann.
if [ ${#VLLM_SERVICES[@]} -gt 0 ] && [ ${#OTHER_SERVICES[@]} -gt 0 ]; then
    log "Gewähre vLLM einen Vorsprung von 10 Sekunden zum Allokieren der GPU-Ressourcen..."
    sleep 10
fi

# --- PHASE 2: Alle restlichen Services starten ---
for service in "${OTHER_SERVICES[@]:+"${OTHER_SERVICES[@]}"}"; do
    case "$service" in
        "flux1")
            start_diffusers "flux1" "main-Flux1" "8890"
            ;;
        "flux2")
            start_diffusers "flux2" "main-Flux2" "8890"
            ;;
        "docling")
            log "Starte Docling Service (Standard-Konfiguration) ..."
            docker compose $ENV_ARG -f "$DOCLING_DIR/docker-compose.yaml" up -d
            ;;
        "infinity")
            log "Starte Infinity Embeddings Service (Standard-Konfiguration) ..."
            docker compose $ENV_ARG -f "$INFINITY_DIR/docker-compose.yaml" up -d
            ;;
    esac
done

log "Alle angeforderten Services wurden verarbeitet."
