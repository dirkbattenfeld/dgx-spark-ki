#!/bin/sh
set -e

CONFIG_PATH="/config/garage.toml"
ENV_FILE="../../.env"
KEY_NAME="rag-key"
BUCKET_NAME="my-rag-bucket"

echo "🔑 Erstelle S3-Key '$KEY_NAME' in Garage..."

# 1. Key in Garage erstellen (und eventuelle "Bereits vorhanden"-Meldungen abfangen)
KEY_OUTPUT=$(docker exec garage_s3 /usr/local/bin/garage -c "$CONFIG_PATH" key create "$KEY_NAME" 2>&1 || true)
echo "$KEY_OUTPUT"

# 2. Access Key ID und Secret Key aus der Ausgabe herausfiltern
# Garage gibt den Access Key nach "Key ID:" oder als ersten Hash/String aus
ACCESS_KEY=$(echo "$KEY_OUTPUT" | grep -i "Key ID" | awk '{print $NF}')
SECRET_KEY=$(echo "$KEY_OUTPUT" | grep -i "Secret key" | awk '{print $NF}')

# Fallback, falls das Format leicht abweicht, holen wir sie über die Key-Liste mit Secret
if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    echo "ℹ️ Lese bestehenden Key aus Garage aus..."
    LIST_OUTPUT=$(docker exec garage_s3 /usr/local/bin/garage -c "$CONFIG_PATH" key list --show-secret)
    ACCESS_KEY=$(echo "$LIST_OUTPUT" | grep "$KEY_NAME" | awk '{print $1}')
    SECRET_KEY=$(echo "$LIST_OUTPUT" | grep "$KEY_NAME" | awk '{print $2}')
fi

if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    echo "❌ Fehler: Konnte Access Key oder Secret Key nicht ermitteln!"
    exit 1
fi

echo "📌 Gefundener Access Key: $ACCESS_KEY"

# 3. Bucket erstellen (falls noch nicht da)
echo "🪣 Erstelle Bucket '$BUCKET_NAME'..."
docker exec garage_s3 /usr/local/bin/garage -c "$CONFIG_PATH" bucket create "$BUCKET_NAME" 2>/dev/null || echo "ℹ️ Bucket existiert bereits."

# 4. Berechtigungen vergeben
echo "🔐 Erteile Lese- und Schreibrechte für '$KEY_NAME' auf '$BUCKET_NAME'..."
docker exec garage_s3 /usr/local/bin/garage -c "$CONFIG_PATH" bucket allow --key "$KEY_NAME" --read --write "$BUCKET_NAME"

# 5. In die .env eintragen (falls noch nicht vorhanden)
if [ -f "$ENV_FILE" ]; then
    if grep -q "AWS_ACCESS_KEY_ID" "$ENV_FILE"; then
        echo "⚠️ AWS_ACCESS_KEY_ID ist bereits in der .env vorhanden. Überspringe das Schreiben."
    else
        echo "" >> "$ENV_FILE"
        echo "# Automatisch generierte Garage S3 Credentials" >> "$ENV_FILE"
        echo "S3_KEY=$ACCESS_KEY" >> "$ENV_FILE"
        echo "S3_SECRET=$SECRET_KEY" >> "$ENV_FILE"
        echo "S3_BUCKET_NAME=$BUCKET_NAME" >> "$ENV_FILE"
        echo "✅ S3-Credentials erfolgreich in die .env geschrieben!"
    fi
else
    echo "⚠️ .env-Datei unter $ENV_FILE nicht gefunden!"
fi
