FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    git \
    curl \
    ca-certificates \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH="/app"

COPY control-plane/gui_dev/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


