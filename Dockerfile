FROM python:3.11-slim

WORKDIR /app

ARG ENABLE_OCR=false
ENV ENABLE_OCR=${ENABLE_OCR}

RUN useradd -m -u 1000 appuser

COPY requirements.txt .
COPY requirements-ocr.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$ENABLE_OCR" = "true" ]; then pip install --no-cache-dir -r requirements-ocr.txt; fi

COPY app/ ./app/
COPY templates/ ./templates/
COPY vig-project-sa-key.json ./vig-project-sa-key.json

RUN mkdir -p output && chown -R appuser:appuser /app

USER appuser

ENV PORT=8000
ENV USE_OCR=false
ENV GOOGLE_CLOUD_STORAGE_BUCKET=megansoft-candidate-assessments
ENV ASSESSMENT_STORAGE_PREFIX=candidate-assessments
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/vig-project-sa-key.json

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
