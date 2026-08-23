FROM nvcr.io/nvidia/pytorch:25.11-py3
WORKDIR /app

# System-Abhängigkeiten (OCR & Bildverarbeitung)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    libtesseract-dev \
    libleptonica-dev \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# NumPy-Fix für Docling-Abhängigkeiten
# Wir deinstallieren die 2.x Version und erzwingen die 1.x Schiene,
# damit cv2 und pyarrow nicht mehr abstürzen.
RUN pip uninstall -y numpy && \
    pip install --no-cache-dir "numpy<2.0"

# Tesserocr Bindings separat kompilieren und installieren
RUN pip install --no-cache-dir tesserocr

# Docling Installation (inkl. HybridChunker für structure-aware Chunking)
RUN pip install --no-cache-dir "docling[accelerate]"

RUN pip install --no-cache-dir \
    uvicorn \
    fastapi \
    python-multipart \
    einops \
    fsspec \
    s3fs

COPY libs /libs
RUN pip install -e /libs

COPY ki-services/docling/app/ .

ENV PYTHONPATH=/app:/libs

# Verhindert, dass der Container jedes mal Modell updates sucht
ENV HF_HUB_OFFLINE=1



