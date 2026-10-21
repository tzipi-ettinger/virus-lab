# One image for the live server (Dev-B plan 2.7): FastAPI serves the API and the
# built frontend from one origin, so production needs no CORS.
#
#   docker build -t virus-lab .
#   docker run --rm -p 8000:8000 -e DATABASE_URL=... -e FRONTEND_ORIGIN=http://localhost:8000 virus-lab
#
# Owner: B

# --- 1. Build the frontend
FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. The server
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY backend/scripts ./scripts
# Synthetic fixtures only: EXTRACTION_PROVIDER=fake reads them, to try the image
# without a Gemini key. The live server runs with gemini.
COPY backend/tests/fixtures/extraction ./tests/fixtures/extraction
COPY --from=frontend /src/frontend/dist ./static

RUN useradd --create-home --uid 10001 app
USER app

# Render sets PORT. --proxy-headers: Render's proxy ends TLS, and says so in
# X-Forwarded-Proto.
ENV STATIC_DIR=/app/static \
    PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*'"]
