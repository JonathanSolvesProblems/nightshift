FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
# The measured results are part of the deployed artifact, not a build artifact.
# Without this the accuracy page renders "eval/screening.json is not present in
# this image", which is the one page in the service whose whole job is to show a
# number somebody outside this repository produced.
COPY eval/ ./eval/
ENV PYTHONPATH=/app/src

# Both entrypoints live in one image so the worker and the web service can never
# drift apart on the screening logic. Cloud Run Jobs override the command.
CMD ["python", "-m", "priorart.web"]
