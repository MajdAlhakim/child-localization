FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Expose port (Fly.io uses 8080 by default; render/local use 8000)
EXPOSE 8080

# Use $PORT env var if set by hosting platform, else fall back to 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
