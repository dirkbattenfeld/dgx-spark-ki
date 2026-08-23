#!/bin/bash

# 1. Aktive Container finden
CONTAINERS=$(docker ps --format "{{.Names}}")
container_array=($CONTAINERS)
count=${#container_array[@]}

if [ $count -eq 0 ]; then
    echo "Keine laufenden Docker-Container gefunden."
    exit 1
fi

SESSION_NAME="docker_logs"

# Bestehende Session killen für sauberen Neustart
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# 2. Erste Pane erstellen (Container 0)
# Wir starten die Session detached (-d)
tmux new-session -d -s "$SESSION_NAME" -n "Logs" "docker logs -f ${container_array[0]}"

# 3. Spezifische Layout-Logik
if [ $count -eq 2 ]; then
    # Zwei Container: Übereinander
    tmux split-window -v -t "$SESSION_NAME" "docker logs -f ${container_array[1]}"

elif [ $count -eq 3 ]; then
    # Drei Container: Oben einer, unten zwei nebeneinander
    # Erst horizontal teilen (unten)
    tmux split-window -v -t "$SESSION_NAME" "docker logs -f ${container_array[1]}"
    # Dann die untere Pane vertikal teilen
    tmux split-window -h -t "$SESSION_NAME" "docker logs -f ${container_array[2]}"

elif [ $count -eq 4 ]; then
    # Vier Container: 2 oben, 2 unten
    # Erst horizontal teilen
    tmux split-window -v -t "$SESSION_NAME" "docker logs -f ${container_array[1]}"
    # Dann oben links splitten
    tmux select-pane -t 0
    tmux split-window -h -t "$SESSION_NAME" "docker logs -f ${container_array[2]}"
    # Dann unten links splitten
    tmux select-pane -t 2
    tmux split-window -h -t "$SESSION_NAME" "docker logs -f ${container_array[3]}"

else
    # Ab 5 Containern: Standard-Kachelung (tiled)
    for (( i=1; i<$count; i++ )); do
        tmux split-window -v -t "$SESSION_NAME" "docker logs -f ${container_array[$i]}"
        tmux select-layout -t "$SESSION_NAME" tiled
    done
fi

# 4. Am Ende zur Session verbinden
tmux attach-session -t "$SESSION_NAME"
