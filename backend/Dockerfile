FROM python:3.11-slim

WORKDIR /srv

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Mirror repo structure so backend.app.main:app resolves correctly
RUN mkdir -p backend
COPY app/ ./backend/app/

EXPOSE 8000

CMD uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
