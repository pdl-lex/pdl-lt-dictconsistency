"""Fortschrittsverfolgung für `/data/db-load` — Auswahlen können mehrere
zehntausend Artikel umfassen und (gemessen: 34.496 Artikel ≈ 80s) mehrere
zehn Sekunden dauern. Ohne Fortschrittsanzeige wartet niemand darauf.

Rein in-Prozess (ein `dict`, kein SQLite-Schema): Jobs sind ephemer und
gehören zu genau einer laufenden Nutzer-Interaktion — ein Prozessneustart
verliert sie, was für diesen Anwendungsfall unproblematisch ist (der Nutzer
klickt „Laden" einfach erneut). Passt zur Ein-Prozess-Annahme, die diese App
an anderer Stelle ohnehin macht (lokales SQLite in `auth/db.py`).
"""
from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

_MAX_AGE_SECONDS = 3600  # alte Jobs (abgeschlossen oder verwaist) verwerfen


@dataclass
class LoadJob:
    id: str
    total: int
    owner_user_id: int
    done: int = 0
    status: str = "running"  # running | ok | error
    error: str | None = None
    result: dict | None = None
    created_at: float = field(default_factory=time.time)


_jobs: dict[str, LoadJob] = {}
_lock = threading.Lock()


def create_job(total: int, *, owner_user_id: int) -> LoadJob:
    job = LoadJob(id=uuid.uuid4().hex, total=total, owner_user_id=owner_user_id)
    with _lock:
        _jobs[job.id] = job
        _prune_locked()
    return job


def get_job(job_id: str) -> LoadJob | None:
    with _lock:
        return _jobs.get(job_id)


def _prune_locked() -> None:
    now = time.time()
    stale = [jid for jid, j in _jobs.items() if now - j.created_at > _MAX_AGE_SECONDS]
    for jid in stale:
        del _jobs[jid]


def run(job: LoadJob, work: Callable[[Callable[[int], None]], dict]) -> None:
    """`work` bekommt einen `on_progress(n)`-Callback, liefert das Endergebnis
    (dieselbe Struktur wie `core.data.materialize_db_selection`) oder wirft."""
    try:
        job.result = work(lambda n: setattr(job, "done", n))
        job.status = "ok"
    except Exception as e:  # noqa: BLE001 — Fehlerursache dem Nutzer zeigen, nicht verschlucken
        job.error = str(e)
        job.status = "error"
