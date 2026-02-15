FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app/ ./app/

USER appuser
EXPOSE 8100

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD ["curl", "-f", "http://localhost:8100/health"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
