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

# FastAPI liefert API unter /api und das Frontend unter / aus.
CMD ["uv", "run", "uvicorn", "pdl_lt_dictconsistency.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
