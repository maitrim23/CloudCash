# One image = API + built UI + a price database baked in at build time.
#   docker build -t costgoblin .      (needs backend/data/prices.db; see "Building the price DB" in study.md)
#   docker run -p 8000:8000 -v costgoblin-data:/data costgoblin

# ---- 1. build the React app ------------------------------------------------
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. runtime ------------------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/data/prices.db ./data/prices.db
COPY --from=ui /ui/dist ./static

# The price DB is read-only and ships in the image. Saved scenarios go to a mounted volume,
# so redeploying the image does not wipe them (on hosts with ephemeral disks they WILL reset).
ENV PRICE_DB=/app/data/prices.db SCENARIO_DB=/data/scenarios.db STATIC_DIR=/app/static COOKIE_SECURE=0
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
# $PORT is set by most PaaS hosts (Render, Fly, Cloud Run); default 8000.
CMD ["sh", "-c", "exec python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
