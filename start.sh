#!/bin/bash

# Parameter auswerten
PARAM="${1:-}"

# Hilfefunktion anzeigen
show_help() {
    echo "Nutzung: $0 [OPTION]"
    echo ""
    echo "Optionen:"
    echo "  (ohne Parameter) Starts tmux Session mit 'git status' & 'docker ps -a' (lokal und gx10)."
    echo "  rag              Führt zusätzlich lokal 'make up gx10 MODE=request' aus."
    echo "  rag_ingestion    Führt zusätzlich lokal 'make up gx10 MODE=ingestion' aus."
    echo "  rag_kombi        Führt zusätzlich lokal 'make up gx10 MODE=kombi' aus."
    echo "  help             Zeigt diese Hilfe an."
    exit 0
}

if [ "$PARAM" = "help" ] || [ "$PARAM" = "-h" ] || [ "$PARAM" = "--help" ]; then
    show_help
fi

# 1. & 2. & 3. tmux session starten und in das Verzeichnis navigieren
tmux new-session -d -s spark_stack -c ~/docker-projects/dgx-spark-ki

# 4. & 5. Standard-Befehle im ersten Fenster (lokal) ausführen
tmux send-keys -t spark_stack:0 'git status' C-m
tmux send-keys -t spark_stack:0 'docker ps -a' C-m

# Je nach Parameter optionalen make-Befehl lokal absetzen
case "$PARAM" in
    rag)
        tmux send-keys -t spark_stack:0 'make up gx10 MODE=request' C-m
        ;;
    rag_ingestion)
        tmux send-keys -t spark_stack:0 'make up gx10 MODE=ingestion' C-m
        ;;
    rag_kombi)
        tmux send-keys -t spark_stack:0 'make up gx10 MODE=kombi' C-m
        ;;
    "")
        # Kein Parameter übergeben – Verhalten bleibt unverändert
        ;;
    *)
        echo "Unbekannter Parameter: $PARAM"
        echo ""
        show_help
        ;;
esac

# 6. & 7. Fenster teilen und in den neuen Bereich wechseln
tmux split-window -h -t spark_stack:0

# 8. & 9. & 10. & 11. & 12. Befehle im rechten Fenster (gx10 via SSH) ausführen
tmux send-keys -t spark_stack:0.1 'ssh gx10' C-m
tmux send-keys -t spark_stack:0.1 'cd docker/dgx-spark-ki' C-m
tmux send-keys -t spark_stack:0.1 'git status' C-m
tmux send-keys -t spark_stack:0.1 'docker ps -a' C-m

# Session anhängen
tmux attach-session -t spark_stack

