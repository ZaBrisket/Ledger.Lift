FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
RUN pip install --upgrade pip && pip install -e .
COPY worker /app/worker
ENTRYPOINT ["python", "-m", "worker.cli"]
