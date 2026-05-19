"""
query_dwds_api.py

Fragt die DWDS-API für jedes Lemma in der Eingabe-CSV ab und speichert
die kanonische Form als zusätzliche Spalte 'lemma-neu'.

Bedeutung von 'lemma-neu':
  (leer)      = noch nicht abgefragt
  <wort>      = kanonische Form laut DWDS; wenn <wort> != lemma -> Altschreibung
  NOT_FOUND   = Wort nicht in DWDS gefunden

Wiederaufnahme: Bereits abgefragte Zeilen (lemma-neu nicht leer) werden
übersprungen, sofern --requery nicht gesetzt ist. Wenn die Ausgabe-Datei
bereits existiert, wird sie als Basis verwendet (Fortsetzung nach Abbruch).

Fehler werden in einer separaten Datei gespeichert und nach dem Hauptdurchlauf
erneut versucht. Nach --max-failures Fehlern (Standard 3) wird ein Wort nicht
mehr abgefragt.

Verwendung:
  uv run python tools/spellings/query_dwds_api.py
  uv run python tools/spellings/query_dwds_api.py --requery --rate-limit 5
  uv run python tools/spellings/query_dwds_api.py --pause-every 1000 --pause-seconds 30
"""

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).parent
DWDS_DIR = HERE / "dwds"
DWDS_API_URL = "https://www.dwds.de/api/wb/snippet/?q="

NOT_FOUND = "NOT_FOUND"
DEFAULT_MAX_FAILURES = 3


# ── API ──────────────────────────────────────────────────────────────────────


def query_canonical(word: str, timeout: float = 10.0) -> tuple[str | None, str | None]:
    """
    Fragt DWDS-API nach der kanonischen Schreibung von *word*.

    Gibt zurück:
      (canonical, None)       bei Erfolg
      (NOT_FOUND, None)       wenn Wort nicht in DWDS
      (None, fehlermeldung)   bei Netzwerk- oder HTTP-Fehler
    """
    url = DWDS_API_URL + urllib.parse.quote(word)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pdl-lt-dictconsistency/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, list) or not data:
            return NOT_FOUND, None
        for entry in data:
            if entry.get("input") == word:
                return entry.get("lemma") or NOT_FOUND, None
        return data[0].get("lemma") or NOT_FOUND, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# ── CSV I/O ──────────────────────────────────────────────────────────────────


def load_csv(path: Path) -> tuple[list[dict], list[str]]:
    """Lädt CSV und gibt (rows, fieldnames) zurück."""
    rows: list[dict] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rows.append(dict(row))
    return rows, fieldnames


def save_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """Schreibt CSV atomar (via temporäre Datei + rename)."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


# ── Fehlerdatei ──────────────────────────────────────────────────────────────


def load_errors(path: Path) -> dict[str, dict]:
    """Lädt Fehlerdatei. Gibt {wort: {count, last_error, timestamp}} zurück."""
    result: dict[str, dict] = {}
    if not path.exists():
        return result
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            w = (row.get("wort") or "").strip()
            if w:
                result[w] = {
                    "count": int(row.get("fehler_count") or 0),
                    "last_error": row.get("letzter_fehler") or "",
                    "timestamp": row.get("timestamp") or "",
                }
    return result


def save_errors(path: Path, errors: dict[str, dict]) -> None:
    """Schreibt Fehlerdatei."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["wort", "fehler_count", "letzter_fehler", "timestamp"])
        for w, info in sorted(errors.items()):
            writer.writerow([w, info["count"], info["last_error"], info["timestamp"]])


# ── Kandidaten ───────────────────────────────────────────────────────────────


def build_candidates(
    rows: list[dict],
    row_index: dict[str, int],
    errors: dict[str, dict],
    requery: bool,
    max_failures: int,
) -> list[tuple[int, str]]:
    """Gibt Liste von (row_idx, lemma) zurück, die abgefragt werden sollen."""
    result = []
    for lemma, row_idx in row_index.items():
        if errors.get(lemma, {}).get("count", 0) >= max_failures:
            continue
        lemma_neu = (rows[row_idx].get("lemma-neu") or "").strip()
        if lemma_neu and not requery:
            continue
        result.append((row_idx, lemma))
    return result


# ── Abfrage-Durchlauf ────────────────────────────────────────────────────────


def run_pass(
    candidates: list[tuple[int, str]],
    rows: list[dict],
    errors: dict[str, dict],
    output_path: Path,
    errors_path: Path,
    fieldnames: list[str],
    delay: float,
    pause_every: int,
    pause_seconds: float,
    save_interval: float,
    label: str,
) -> int:
    """
    Führt einen Abfrage-Durchlauf über *candidates* durch.
    Gibt die Anzahl neu gefundener Alt→Neu-Paare zurück.
    """
    pairs_found = 0
    query_count = 0
    last_save = time.time()
    start_time = time.time()
    total = len(candidates)

    def flush() -> None:
        save_csv(output_path, rows, fieldnames)
        save_errors(errors_path, errors)

    for idx, (row_idx, lemma) in enumerate(candidates, 1):
        # Fortschrittsanzeige
        elapsed = time.time() - start_time
        rate = idx / elapsed if elapsed > 0 else 0
        eta_s = (total - idx) / rate if rate > 0 else 0
        print(
            f"\r  {label} [{idx:>{len(str(total))}}/{total}]  "
            f"{lemma:<40}  {pairs_found} Paare  ETA {eta_s / 60:.0f}min  ",
            end="", flush=True,
        )

        canonical, error = query_canonical(lemma)
        query_count += 1

        if error:
            if lemma not in errors:
                errors[lemma] = {"count": 0, "last_error": "", "timestamp": ""}
            errors[lemma]["count"] += 1
            errors[lemma]["last_error"] = error
            errors[lemma]["timestamp"] = datetime.now().isoformat(timespec="seconds")

            if "429" in error:
                print(f"\n  Rate-Limit (429)! Pausiere 60s...", flush=True)
                time.sleep(60)
        else:
            rows[row_idx]["lemma-neu"] = canonical
            if canonical and canonical != lemma and canonical != NOT_FOUND:
                pairs_found += 1
            errors.pop(lemma, None)  # Fehler als gelöst markieren

        time.sleep(delay)

        if pause_every and query_count % pause_every == 0:
            print(f"\n  Reguläre Pause ({pause_seconds}s nach {query_count} Abfragen)...", flush=True)
            time.sleep(pause_seconds)

        if time.time() - last_save >= save_interval:
            flush()
            last_save = time.time()

    flush()

    errors_this_pass = sum(1 for w in errors if errors[w]["timestamp"].startswith(datetime.now().strftime("%Y-%m-%d")))
    print(f"\n  {label} abgeschlossen: {pairs_found} neue Paare, {query_count} Abfragen.")
    return pairs_found


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    csv_files = sorted(DWDS_DIR.glob("*.csv"), reverse=True)
    default_input = str(csv_files[0]) if csv_files else ""
    default_output = str(DWDS_DIR / (csv_files[0].stem + "-api.csv")) if csv_files else "output.csv"

    parser = argparse.ArgumentParser(
        description="Fragt DWDS-API für jedes Lemma ab und ergänzt Spalte 'lemma-neu'.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input",         default=default_input,
                        help="Eingabe-CSV (DWDS-Lemmataliste)")
    parser.add_argument("--output",        default=default_output,
                        help="Ausgabe-CSV (mit lemma-neu Spalte)")
    parser.add_argument("--errors",        default=str(HERE / "dwds_api_errors.csv"),
                        help="Fehlerdatei (Semikolon-getrennt)")
    parser.add_argument("--requery",       action="store_true",
                        help="Bereits abgefragte Wörter erneut abfragen")
    parser.add_argument("--rate-limit",    type=float, default=2.0, metavar="REQ/S",
                        help="Abfragen pro Sekunde")
    parser.add_argument("--pause-every",   type=int,   default=0,   metavar="N",
                        help="Reguläre Pause nach je N Abfragen (0 = keine)")
    parser.add_argument("--pause-seconds", type=float, default=5.0,
                        help="Dauer der regulären Pause in Sekunden")
    parser.add_argument("--save-interval", type=float, default=10.0,
                        help="Speichern alle N Sekunden")
    parser.add_argument("--max-failures",  type=int,   default=DEFAULT_MAX_FAILURES,
                        help="Max. Fehlerversuche pro Wort vor dauerhaftem Überspringen")
    parser.add_argument("--start",         type=int,   default=0,
                        help="Erster Kandidaten-Index (0-basiert, inklusiv)")
    parser.add_argument("--end",           type=int,   default=None,
                        help="Letzter Kandidaten-Index (exklusiv; Standard: bis zum Ende)")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)
    errors_path = Path(args.errors)
    delay       = 1.0 / args.rate_limit

    print("=== DWDS API Query ===")
    print(f"  Eingabe      : {input_path.name}")
    print(f"  Ausgabe      : {output_path}")
    print(f"  Fehler       : {errors_path}")
    print(f"  Rate         : {args.rate_limit} req/s  (Delay {delay:.3f}s)")
    if args.pause_every:
        print(f"  Pause        : {args.pause_seconds}s nach je {args.pause_every} Abfragen")
    print(f"  Speichern    : alle {args.save_interval}s")
    print(f"  Requery      : {args.requery}")
    print(f"  Max. Fehler  : {args.max_failures}")
    if args.start or args.end is not None:
        end_label = args.end if args.end is not None else "Ende"
        print(f"  Range        : [{args.start}, {end_label})")
    print()

    # Basis laden: Output wenn vorhanden (Fortsetzung), sonst Input
    base_path = output_path if output_path.exists() else input_path
    mode = "Fortsetzung" if output_path.exists() else "Neu"
    print(f"Lade {mode}: {base_path.name}")
    rows, fieldnames = load_csv(base_path)
    print(f"  {len(rows):,} Zeilen.")

    # lemma-neu Spalte hinzufügen falls fehlend
    if "lemma-neu" not in fieldnames:
        fieldnames.append("lemma-neu")
        for row in rows:
            row.setdefault("lemma-neu", "")

    # Index aufbauen: lemma -> row_idx (nur gültige Einzel-Lemmata)
    row_index: dict[str, int] = {}
    for i, row in enumerate(rows):
        lemma = (row.get("lemma") or "").strip()
        if not lemma or " " in lemma or lemma[0] in "-+":
            continue
        if not all(c.isalpha() or c == "-" for c in lemma):
            continue
        row_index[lemma] = i

    # Fehler laden
    errors = load_errors(errors_path)
    if errors:
        print(f"  {len(errors)} Fehlereinträge geladen.")

    # Kandidaten bestimmen und ggf. auf Range einschränken
    candidates = build_candidates(rows, row_index, errors, args.requery, args.max_failures)
    total_candidates = len(candidates)
    candidates = candidates[args.start:args.end]
    already_done = sum(1 for r in rows if (r.get("lemma-neu") or "").strip() and not args.requery)
    max_failures_reached = sum(1 for w, e in errors.items() if e["count"] >= args.max_failures)

    print(f"\nKandidaten     : {len(candidates):,}  (gesamt gefiltert: {total_candidates:,})")
    print(f"Bereits fertig : {already_done:,}")
    if max_failures_reached:
        print(f"Dauerhaft Skip : {max_failures_reached} (≥{args.max_failures} Fehler)")

    if not candidates:
        print("\nNichts zu tun.")
        return

    eta_s = len(candidates) / args.rate_limit
    print(f"Geschätzte Laufzeit: {eta_s / 3600:.1f}h ({eta_s / 60:.0f}min)")
    print()

    # ── Hauptdurchlauf ────────────────────────────────────────────────────
    run_pass(
        candidates, rows, errors, output_path, errors_path, fieldnames,
        delay, args.pause_every, args.pause_seconds, args.save_interval,
        label="Hauptdurchlauf",
    )

    # ── Wiederholungsversuche ─────────────────────────────────────────────
    retry_round = 0
    while True:
        retry_cands = [
            (row_index[w], w)
            for w, e in errors.items()
            if e["count"] < args.max_failures and w in row_index
        ]
        if not retry_cands:
            break
        retry_round += 1
        print(f"\nRetry-Runde {retry_round}: {len(retry_cands)} Wörter (doppeltes Delay)...")
        run_pass(
            retry_cands, rows, errors, output_path, errors_path, fieldnames,
            delay * 2, args.pause_every, args.pause_seconds, args.save_interval,
            label=f"Retry {retry_round}",
        )
        if retry_round >= args.max_failures:
            break

    # ── Endstatistik ──────────────────────────────────────────────────────
    total_checked = sum(1 for r in rows if (r.get("lemma-neu") or "").strip())
    total_pairs = sum(
        1 for r in rows
        if (r.get("lemma-neu") or "") not in ("", NOT_FOUND)
        and r.get("lemma-neu") != r.get("lemma")
    )
    final_errors = sum(1 for e in errors.values() if e["count"] >= args.max_failures)

    print(f"\n=== Fertig ===")
    print(f"  Abgefragt          : {total_checked:,}")
    print(f"  Alt->Neu-Paare     : {total_pairs:,}")
    print(f"  Dauerhaft fehlgesch.: {final_errors}")
    print(f"  Ausgabe            : {output_path}")
    print(f"  Fehler             : {errors_path}")


if __name__ == "__main__":
    main()
