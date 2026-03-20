FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml /app/pyproject.toml
COPY services /app/services
COPY sdk /app/sdk
COPY models /app/models

RUN uv sync --all-packages

ENV PYTHONPATH=/app
