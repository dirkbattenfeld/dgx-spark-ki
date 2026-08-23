#!/bin/bash

# 1. Sicherstellen, dass pipx installiert und einsatzbereit ist
if ! command -v pipx &> /dev/null; then
    echo "pipx nicht gefunden. Installiere pipx..."
    python3 -m pip install --user pipx
    # Pfade für pipx in der aktuellen Shell-Sitzung verfügbar machen
    python3 -m pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Aider isoliert über pipx installieren
if ! command -v aider &> /dev/null; then
    echo "Installiere Aider isoliert via pipx..."
    pipx install aider-chat
else
    echo "Aider ist bereits via pipx installiert."
fi

# 3. .aider.conf.yml im Monorepo-Wurzelverzeichnis anlegen (falls nicht vorhanden)
if [ ! -f /workspace/.aider.conf.yml ]; then
    echo "Erstelle .aider.conf.yml in /workspace..."
    echo "auto-commits: false" > /workspace/.aider.conf.yml
fi

# 4. Umgebungsvariablen für das GX10-Backend setzen
export OPENAI_API_BASE="http://gx10:8888/v1"
export OPENAI_API_KEY="none"

# 5. Aider auf Root-Ebene des Monorepos starten
echo "Starte Aider für das gesamte Monorepo..."
cd /workspace
# Wenn das matchen der generierten Blöcke nicht funktioniert dann --edit-format unified
aider --editor --edit-format diff --model openai/RedHatAI/Qwen3-Coder-Next-NVFP4
