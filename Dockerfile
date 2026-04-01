FROM python:3.11-slim

# System dependencies:
#   poppler-utils  — pdf2image (PDF → image conversion)
#   libgl1         — OpenCV (EasyOCR dependency)
#   libglib2.0-0   — GLib (EasyOCR / OpenCV dependency)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create non-root user early so model pre-download uses the correct home directory
RUN useradd -m -u 1000 appuser

# Install Python deps first — better layer caching on code-only changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download EasyOCR English model as appuser so models land in /home/appuser/.EasyOCR
# and are found at runtime (avoids cold-start download timeout on Cloud Run)
RUN su appuser -c "python -c \"import easyocr; easyocr.Reader(['en'], gpu=False)\"" \
    || echo "WARNING: EasyOCR model pre-download failed — will download at runtime"

# Copy only what the app needs at runtime
COPY app/ ./app/
COPY templates/ ./templates/

# Create output dir and hand everything to appuser
RUN mkdir -p output && chown -R appuser:appuser /app

USER appuser

# Cloud Run injects PORT at runtime; default to 8000 for local runs
ENV PORT=8000

EXPOSE 8000

# Shell form required so $PORT is expanded at runtime
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
