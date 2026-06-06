FROM python:3.11-slim

WORKDIR /app

RUN groupadd --system appuser && useradd --system --gid appuser appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN mkdir -p /data && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 9103

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9103/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9103"]
