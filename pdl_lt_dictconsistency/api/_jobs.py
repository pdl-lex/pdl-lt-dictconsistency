"""Generischer In-Prozess-Job-Store für langsame Prüfungen (Fortschritt per Polling).

Vorbild ist `wbdb/load_jobs.py` (dort speziell für `/data/db-load`) — hier
ohne wbdb-Bezug und mit einem zusätzlichen `phase`-Feld, damit ein Job seinen
Fortschritt in mehreren benannten Phasen melden kann (z. B. „scanning" dann
„checking" bei der Verweisprüfung, `core/references.py`). Rein in-Prozess
(ein `dict`, kein SQLite-Schema): Jobs sind ephemer und gehören zu genau
einer laufenden Nutzer-Interaktion — ein Prozessneustart verliert sie, was
unproblematisch ist (der Nutzer startet die Prüfung einfach erneut).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

_MAX_AGE_SECONDS = 3600  # alte Jobs (abgeschlossen oder verwaist) verwerfen


@dataclass
class Job:
    id: str
    total: int
    owner_user_id: int | None
    phase: str = ""
    done: int = 0
    status: str = "running"  # running | ok | error
    error: str | None = None
    result: dict | None = None
    created_at: float = field(default_factory=time.time)


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create_job(total: int, *, owner_user_id: int | None, phase: str = "") -> Job:
    job = Job(id=uuid.uuid4().hex, total=total, owner_user_id=owner_user_id, phase=phase)
    with _lock:
        _jobs[job.id] = job
        _prune_locked()
    return job


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def _prune_locked() -> None:
    now = time.time()
    stale = [jid for jid, j in _jobs.items() if now - j.created_at > _MAX_AGE_SECONDS]
    for jid in stale:
        del _jobs[jid]


def update_progress(job: Job, *, phase: str, done: int, total: int) -> None:
    job.phase = phase
    job.done = done
    job.total = total


def finish_ok(job: Job, result: dict) -> None:
    job.result = result
    job.status = "ok"


def finish_error(job: Job, error: Exception) -> None:
    job.error = str(error)
    job.status = "error"
