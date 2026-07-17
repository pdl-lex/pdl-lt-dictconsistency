"""FastAPI-Einstiegspunkt der Prüf-API.

Start:  uv run uvicorn pdl_lt_dictconsistency.api.main:app --reload
Docs:   http://localhost:8000/docs
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import (
    data,
    nesting,
    pathfinder,
    senses_stats,
    spelling,
    tag_content,
    uniqueness,
    validator,
)

app = FastAPI(
    title="LexoTerm Tools — Prüf-API",
    description="XML-Wörterbuch-Konsistenzprüfungen als REST-API.",
    version="0.1.0",
)

# Für das künftige React+Vite-Frontend (Dev-Server). In Produktion einschränken.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"], include_in_schema=False)
@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Liveness-Check (auch unter /health, z. B. für Container-Healthchecks)."""
    return {"status": "ok"}


for module in (data, uniqueness, nesting, pathfinder, senses_stats, validator, tag_content, spelling):
    app.include_router(module.router, prefix="/api")


# In Produktion das gebaute Frontend (frontend/dist) unter "/" ausliefern.
# Nur mounten, wenn der Build existiert — im Dev läuft das Frontend separat (Vite).
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
