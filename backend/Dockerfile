FROM python:3.11-slim

WORKDIR /srv

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Mirror the repo's backend/app/ structure so that
# "from backend.app.core.config import settings" resolves correctly
RUN mkdir -p backend
COPY app/ ./backend/app/

# Expose port — GCP/local default is 8000; Fly.io injects PORT=8080 at runtime
EXPOSE 8000

# Use $PORT env var if set by hosting platform, else fall back to 8000
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
