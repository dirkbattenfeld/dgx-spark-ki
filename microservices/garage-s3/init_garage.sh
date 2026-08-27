#!/bin/sh
set -e

echo "🚀 Starte Garage S3 für die Ersteinrichtung..."

# Container im Hintergrund starten
docker compose --env-file ../../.env up -d garage

echo "⏳ Warte, bis der Garage-Server bereit ist..."

# Warten, bis 'garage status' erfolgreich durchläuft (zeigt an, dass der Server antwortet)
COUNTER=0
while ! docker exec garage_s3 /usr/local/bin/garage -c /config/garage.toml status >/dev/null 2>&1; do
    COUNTER=$((COUNTER + 1))
    if [ "$COUNTER" -gt 15 ]; then
        echo "❌ Fehler: Garage-Server ist nicht rechtzeitig hochgefahren."
        exit 1
    fi
    sleep 3
    printf "."
done
echo ""
echo "✅ Garage-Server antwortet!"

# 1. Status prüfen (sollte er schon konfiguriert sein)
if docker exec garage_s3 /usr/local/bin/garage -c /config/garage.toml status 2>/dev/null | grep -q "available"; then
    echo "✅ Garage S3 ist bereits konfiguriert und einsatzbereit."
    exit 0
fi

echo "⚙️ Führe automatisches Single-Node-Setup aus..."

# 2. Connect-String sauber auslesen
CONNECT_STRING=$(docker exec garage_s3 /usr/local/bin/garage -c /config/garage.toml node id | grep -E '^[0-9a-f]{64}@')

if [ -z "$CONNECT_STRING" ]; then
    CONNECT_STRING=$(docker exec garage_s3 /usr/local/bin/garage -c /config/garage.toml node id | head -n 1)
fi

NODE_HASH=$(echo "$CONNECT_STRING" | cut -d'@' -f1)

if [ -z "$NODE_HASH" ]; then
    echo "❌ Fehler: Konnte Node ID nicht abrufen!"
    exit 1
fi

echo "📌 Gefundener Connect-String: $CONNECT_STRING"

# 3. Befehle ausführen
docker exec garage_s3 /usr/local/bin/garage -c /config/garage.toml node connect "$CONNECT_STRING"
docker exec garage_s3 /usr/local/bin/garage -c /config/garage.toml layout assign "$NODE_HASH" --zone local-zone --capacity 50G
docker exec garage_s3 /usr/local/bin/garage -c /config/garage.toml layout apply --version 1

echo "✅ Garage S3 wurde erfolgreich initialisiert und ist einsatzbereit!"
