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
from ..wbdb import index_store
from ..wbdb.connection import close_pool, init_pool
from .routers import (
    admin,
    auth,
    data,
    db_index,
    nesting,
    pathfinder,
    senses_stats,
    spelling,
    tag_content,
    uniqueness,
    validator,
    xml_structure,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    index_store.init_db()
    init_pool()
    yield
    close_pool()


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
for module in (data, db_index, uniqueness, nesting, pathfinder, senses_stats, validator, tag_content, spelling, xml_structure):
    app.include_router(module.router, prefix="/api")


class _HttpOnlyStaticFiles(StaticFiles):
    """StaticFiles lehnt Nicht-HTTP-Scopes (z. B. WebSocket-Handshakes) sonst
    mit einem unbehandelten AssertionError ab, statt sauber abzulehnen — z. B.
    wenn eine Browser-Erweiterung einen WS-Verbindungsversuch auf einen nicht
    geroutet Pfad macht. Vor dem `accept()` gesendetes `websocket.close` lässt
    uvicorn den Handshake stattdessen mit HTTP 403 beantworten."""

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1000})
            return
        await super().__call__(scope, receive, send)


# In Produktion das gebaute Frontend (frontend/dist) unter "/" ausliefern.
# Nur mounten, wenn der Build existiert — im Dev läuft das Frontend separat (Vite).
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", _HttpOnlyStaticFiles(directory=str(_DIST), html=True), name="frontend")
