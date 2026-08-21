"""FastAPI-Einstiegspunkt der Prüf-API.

Start:  uv run uvicorn pdl_lt_dictconsistency.api.main:app --reload
Docs:   http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..auth.db import init_db
from .routers import (
    admin,
    auth,
    data,
    nesting,
    pathfinder,
    senses_stats,
    spelling,
    tag_content,
    uniqueness,
    validator,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="LexoTerm Tools — Prüf-API",
    description="XML-Wörterbuch-Konsistenzprüfungen als REST-API.",
    version="0.1.0",
    lifespan=lifespan,
)

# Keine CORS-Middleware: Dev-Server proxyt /api (Vite → uvicorn), Produktion
# liefert Frontend und API vom selben Origin aus (siehe unten) — beides
# same-origin, und Cookie-Sessions (auth.sessions) brauchen ohnehin keine
# Cross-Origin-Freigabe.


@app.get("/health", tags=["meta"], include_in_schema=False)
@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Liveness-Check (auch unter /health, z. B. für Container-Healthchecks)."""
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
for module in (data, uniqueness, nesting, pathfinder, senses_stats, validator, tag_content, spelling):
    app.include_router(module.router, prefix="/api")


# In Produktion das gebaute Frontend (frontend/dist) unter "/" ausliefern.
# Nur mounten, wenn der Build existiert — im Dev läuft das Frontend separat (Vite).
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
