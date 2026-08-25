FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src

# Both entrypoints live in one image so the worker and the web service can never
# drift apart on the screening logic. Cloud Run Jobs override the command.
CMD ["python", "-m", "priorart.web"]
