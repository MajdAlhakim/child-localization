FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Expose port — GCP/local default is 8000; Fly.io injects PORT=8080 at runtime
EXPOSE 8000

# Use $PORT env var if set by hosting platform, else fall back to 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
