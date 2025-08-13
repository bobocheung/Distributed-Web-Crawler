FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN python -m venv .venv && . .venv/bin/activate && pip install --upgrade pip setuptools wheel && pip install -r requirements.txt
COPY . /app
ENV PATH="/app/.venv/bin:$PATH"
# gunicorn app factory call
CMD ["gunicorn", "backend.app:create_app()", "-b", "0.0.0.0:5000", "-w", "4"]
