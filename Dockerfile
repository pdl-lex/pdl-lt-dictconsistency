# ---- Stage 1: Frontend bauen (React + Vite) ----
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Backend (FastAPI) + statisches Frontend ----
FROM python:3.14-slim
WORKDIR /app

# uv für Dependency-Management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Python-Dependencies (ohne Dev-Gruppe)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Backend-Code (core/ + api/) und Wortlisten
COPY pdl_lt_dictconsistency/ ./pdl_lt_dictconsistency/
COPY tools/ ./tools/

# Gebautes Frontend an den von main.py erwarteten Ort
COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000

# Alle persistenten Daten dieser App liegen unter /data — auf dem Server per
# Bind-Mount auf /wb/data/apps/pdl-lt-dictconsistency/ (analog zu
# /wb/data/apps/pdl-lt-wbdb/ im wbdb-Repo). Ohne diesen Mount (z. B. lokal ohne
# Docker) ist der Pfad einfach ein normales, unbeschränktes Verzeichnis.
#
# LT_DATA_ROOTS: Scan- und Prüf-Endpunkte lehnen andere Pfade mit 403 ab
# (Upload-Sessions bleiben davon unberührt). Zur Laufzeit überschreibbar:
# docker run -e LT_DATA_ROOTS=… Lokale Entwicklung (ohne Docker) bleibt
# unbeschränkt.
# LT_LOCAL_DB_PATH: lokale Accounts/Sessions (pdl_lt_dictconsistency/auth/db.py).
# Ohne persistenten Mount hier würde jeder Neustart alle Accounts löschen.
ENV LT_DATA_ROOTS=/data
ENV LT_LOCAL_DB_PATH=/data/local.db

# FastAPI liefert API unter /api und das Frontend unter / aus.
CMD ["uv", "run", "uvicorn", "pdl_lt_dictconsistency.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
