# Sentinel — production image. Build context is the sentinel/ root so both backend and frontend
# are available (main.py resolves ../frontend). Cloud Run injects $PORT (default 8080).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Install deps first for better layer caching.
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code: backend at /app, frontend at /frontend (sibling, matching local layout).
COPY backend /app
COPY frontend /frontend

# Run as a non-root user.
RUN useradd -m sentinel && chown -R sentinel /app /frontend
USER sentinel

EXPOSE 8080
# Shell form so ${PORT} (set by Cloud Run) is expanded; defaults to 8080 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
