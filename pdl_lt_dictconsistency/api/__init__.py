"""Eigenständige FastAPI-Schicht über der core-Prüflogik.

Reflex-unabhängig. Lokal startbar mit:

    uv run uvicorn pdl_lt_dictconsistency.api.main:app --reload

Jede Prüfung ist ein dünner Wrapper um einen core-Generator und teilt sich
mit der (Übergangs-)Reflex-Oberfläche denselben Code.
"""
