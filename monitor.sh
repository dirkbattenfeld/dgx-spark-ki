#!/bin/bash

# Name für die tmux-Session
SESSION_NAME="sysmon"

# Prüfen, ob die Session bereits existiert.
# Falls ja, einfach verbinden, anstatt sie doppelt zu starten.
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux attach-session -t "$SESSION_NAME"
    exit 0
fi

# 1. Neue tmux-Session im Hintergrund (detached) starten
tmux new-session -d -s "$SESSION_NAME" -n "Performance"

# 2. btop im oberen Bereich (Pane 0) starten
tmux send-keys -t "$SESSION_NAME:0.0" "btop" C-m

# 3. Bildschirm horizontal unterteilen (oben/unten)
tmux split-window -v -t "$SESSION_NAME:0.0"

# 4. nvtop im unteren Bereich (Pane 1) starten
tmux send-keys -t "$SESSION_NAME:0.1" "nvtop" C-m

# 5. Optional: Layout ausrichten (gleiche Größe für beide Hälften)
tmux select-layout -t "$SESSION_NAME:0" even-vertical

# 6. In die erstellte Session wechseln
tmux attach-session -t "$SESSION_NAME"

