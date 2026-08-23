# 1. Referenz auf dein bereits gebautes Basisimage
FROM ai-pipeline-base-gx10:v1.1

# 2. Da im Basisimage am Ende 'USER appuser' gesetzt wurde,
# müssen wir für Installationen kurzzeitig zurück zu root wechseln.
USER root

# 3. Installation der zusätzlichen Bibliothek
# Wir nutzen uv, das bereits im Basisimage unter /uvbin/uv liegt
RUN UV_LINK_MODE=copy /uvbin/uv pip install --system --no-cache-dir qdrant-client

# 4. Wieder zurück zum sicheren User wechseln
USER appuser
