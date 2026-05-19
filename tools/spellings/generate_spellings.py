"""
generate_spellings.py

Erzeugt spellings.csv (alt->neu-Paare) und whitelist.csv (korrekte ß-Woerter)
aus der DWDS-Lemmaliste (tools/spellings/dwds/*.csv) plus supplement.csv
(manuell gepflegte Eintraege fuer Getrenntschreibung, Sonstiges etc.).

Algorithmus fuer ß->ss:
  Fuer jedes Lemma aus DWDS das 'ß' enthaelt: Ersetze 'ß' durch 'ss'.
  Existiert die ss-Form ebenfalls in DWDS -> Altschreibung (Paar).
  Existiert sie nicht -> ß-Schreibung korrekt (Whitelist).

Algorithmus fuer ph->f:
  Fuer jedes Lemma aus DWDS das 'ph' enthaelt: Ersetze 'ph' durch 'f'.
  Existiert die f-Form ebenfalls in DWDS -> Altschreibung (Paar).
  Existiert sie nicht -> ph-Schreibung bleibt (Physik, Philosophie etc.).

Whitelist:
  Alle DWDS-Lemmata mit 'ß', fuer die keine ss-Version in DWDS existiert.

API-Validierung (--api):
  Kandidatenpaare werden per DWDS /api/wb/snippet/ geprueft. Das Ergebnis
  ist autoritativer als die Heuristik: falsche Paare (Maß/Mass) werden
  automatisch erkannt, Neuformen direkt aus DWDS uebernommen.
  Mit --rate-limit REQ/S laesst sich die Anfragerate steuern (Standard: 2.0).

Verwendung:
  uv run python tools/spellings/generate_spellings.py
  uv run python tools/spellings/generate_spellings.py --api
  uv run python tools/spellings/generate_spellings.py --api --rate-limit 5

Abhaengigkeiten: keine externen (nur stdlib)
"""

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent

DWDS_DIR       = HERE / "dwds"
SUPPLEMENT_CSV = HERE / "supplement.csv"
SPELLINGS_CSV  = HERE / "spellings.csv"
WHITELIST_CSV  = HERE / "whitelist.csv"

# ss-Woerter die trotz ss-Pendants in DWDS KEINE Altschreibungen sind:
# Das ss-Pendant ist ein anderes Wort mit anderer Bedeutung/Herkunft.
EXCLUDE_FROM_PAIRS: frozenset[str] = frozenset({
    # ß/ss: ss-Pendant ist ein anderes Wort mit anderer Bedeutung
    "Maß",    # langes a -> ss bleibt; Mass (die Mass = Liter Bier) ist ein anderes Wort
    # ph/f: f-Pendant ist ein anderes Wort mit anderer Bedeutung
    "Phase",  # Phase (Stadium) != Fase (Schrägkante)
    "Phiale", # Phiale (griech. Schale) != Fiale (got. Fiale/Türmchen)
})


# ── Hilfsfunktionen ────────────────────────────────────────────────────────


def load_dwds() -> set[str]:
    """Laedt neueste DWDS-Lemmaliste aus dwds/ und gibt bereinigten Lemma-Set zurueck."""
    csv_files = sorted(DWDS_DIR.glob("*.csv"), reverse=True)
    if not csv_files:
        raise FileNotFoundError(f"Keine CSV-Datei in {DWDS_DIR} gefunden.")
    csv_path = csv_files[0]
    print(f"  Datei: {csv_path.name}")

    words: set[str] = set()
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lemma = (row.get("lemma") or "").strip()
            if not lemma:
                continue
            # Affixe (beginnen mit - oder +)
            if lemma[0] in "-+":
                continue
            # Mehrwortausdruecke ueberspringen
            if " " in lemma:
                continue
            # Nur Buchstaben und Bindestrich (keine $, %, Ziffern etc.)
            if not all(c.isalpha() or c == "-" for c in lemma):
                continue
            words.add(lemma)

    print(f"  {len(words)} Lemmata geladen.")
    return words


def generate_ss_pairs(
    dwds_words: set[str],
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Erzeugt alt->neu-Paare fuer ss/ss aus DWDS-Lemmaliste.

    Fuer jedes ss-Lemma in DWDS: Wenn auch die ss-Version (ss->ss) in DWDS
    existiert, ist das ss-Lemma eine Altschreibung (Paar bilden).
    Sonst ist die ss-Schreibung in neuer Rechtschreibung korrekt (Whitelist).
    """
    pairs: list[tuple[str, str]] = []
    whitelist: list[str] = []

    for word in sorted(dwds_words):
        if "ß" not in word:
            continue
        if word in EXCLUDE_FROM_PAIRS:
            whitelist.append(word)
            continue
        ss_form = word.replace("ß", "ss")
        if ss_form in dwds_words:
            pairs.append((word, ss_form))
        else:
            whitelist.append(word)

    return pairs, whitelist


def generate_ph_pairs(dwds_words: set[str]) -> list[tuple[str, str]]:
    """
    Erzeugt alt->neu-Paare fuer ph->f aus DWDS-Lemmaliste.

    Fuer jedes ph-Lemma in DWDS: Wenn auch die f-Version (ph->f) in DWDS
    existiert, ist das ph-Lemma eine Altschreibung (Paar bilden).
    Woerter wie Physik, Philosophie haben kein f-Pendant -> bleiben unveraendert.
    """
    pairs: list[tuple[str, str]] = []

    for word in sorted(dwds_words):
        if "ph" not in word.lower():
            continue
        if word in EXCLUDE_FROM_PAIRS:
            continue
        f_form = word.replace("Ph", "F").replace("ph", "f")
        if f_form in dwds_words:
            pairs.append((word, f_form))

    return pairs


def load_supplement() -> list[tuple[str, str]]:
    """Laedt manuell gepflegte Paare aus supplement.csv."""
    if not SUPPLEMENT_CSV.exists():
        print("  supplement.csv nicht gefunden, uebersprungen.")
        return []
    pairs: list[tuple[str, str]] = []
    with open(SUPPLEMENT_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            alt = (row.get("alt") or "").strip()
            neu = (row.get("neu") or "").strip()
            if alt and neu:
                pairs.append((alt, neu))
    print(f"  {len(pairs)} Supplement-Eintraege geladen.")
    return pairs


def write_spellings(pairs: list[tuple[str, str]]) -> None:
    """Schreibt spellings.csv (Spalten: alt;neu), sortiert nach Altform."""
    deduped: dict[str, str] = {}
    for old, new in pairs:
        if old not in deduped:
            deduped[old] = new
    sorted_pairs = sorted(deduped.items(), key=lambda x: x[0].lower())
    with open(SPELLINGS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["alt", "neu"])
        writer.writerows(sorted_pairs)
    print(f"  {len(sorted_pairs)} Eintraege -> {SPELLINGS_CSV.name}")


def write_whitelist(words: list[str]) -> None:
    """Schreibt whitelist.csv (Spalte: wort), sortiert."""
    unique = sorted(set(words), key=str.lower)
    with open(WHITELIST_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["wort"])
        for w in unique:
            writer.writerow([w])
    print(f"  {len(unique)} Eintraege -> {WHITELIST_CSV.name}")


# ── DWDS-API ───────────────────────────────────────────────────────────────


def query_dwds_canonical(word: str, timeout: float = 10.0) -> str | None:
    """
    Fragt DWDS /api/wb/snippet/ nach der kanonischen Schreibung.
    Gibt das Lemma zurueck (kann gleich word sein = korrekte Schreibung),
    oder None bei Netzwerkfehler / Wort nicht gefunden.
    """
    url = "https://www.dwds.de/api/wb/snippet/?q=" + urllib.parse.quote(word)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pdl-lt-dictconsistency/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, list) or not data:
            return None
        for entry in data:
            if entry.get("input") == word:
                return entry.get("lemma") or None
        return data[0].get("lemma") or None
    except Exception:
        return None


def api_validate_pairs(
    pairs: list[tuple[str, str]],
    rate_limit: float,
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Validiert Kandidatenpaare per DWDS-API.

    Gibt zurueck:
    - Bereinigte Paare (mit API-korrigierten Neuformen)
    - Woerter, die laut API korrekt geschrieben sind (fuer Whitelist)
    """
    delay = 1.0 / rate_limit
    validated: list[tuple[str, str]] = []
    newly_correct: list[str] = []
    fallback = 0

    total = len(pairs)
    for i, (alt, neu) in enumerate(pairs, 1):
        print(f"\r  [{i}/{total}] {alt:<30}", end="", flush=True)
        canonical = query_dwds_canonical(alt)
        if canonical is None:
            validated.append((alt, neu))
            fallback += 1
        elif canonical == alt:
            newly_correct.append(alt)
        else:
            validated.append((alt, canonical))
        time.sleep(delay)

    print(
        f"\r  {total} Paare geprueft: {len(validated)} bestaetigt/korrigiert, "
        f"{len(newly_correct)} als korrekt erkannt, {fallback} Fallback (API nicht verfuegbar)."
    )
    return validated, newly_correct


# ── Hauptprogramm ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Erzeugt spellings.csv und whitelist.csv aus DWDS-Lemmaliste."
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="DWDS-API zur Validierung/Korrektur der Kandidatenpaare verwenden.",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=2.0,
        metavar="REQ/S",
        help="API-Anfragen pro Sekunde (Standard: 2.0). Nur mit --api wirksam.",
    )
    args = parser.parse_args()

    print("=== generate_spellings.py ===\n")

    # 1. DWDS-Lemmaliste laden
    print("Lade DWDS-Lemmaliste...")
    dwds_words = load_dwds()

    # 2. ß/ss-Paare und Whitelist aus DWDS erzeugen
    print("\nErzeuge ß/ss-Paare aus DWDS...")
    ss_pairs, whitelist_words = generate_ss_pairs(dwds_words)
    print(f"  {len(ss_pairs)} Paare, {len(whitelist_words)} Whitelist-Eintraege.")

    # 3. ph->f-Paare aus DWDS erzeugen
    print("\nErzeuge ph->f-Paare aus DWDS...")
    ph_pairs = generate_ph_pairs(dwds_words)
    print(f"  {len(ph_pairs)} Paare.")

    # 4. Optional: API-Validierung der Heuristik-Kandidaten
    if args.api:
        heuristic_pairs = ss_pairs + ph_pairs
        minutes = len(heuristic_pairs) / args.rate_limit / 60
        print(
            f"\nAPI-Validierung ({len(heuristic_pairs)} Paare, "
            f"{args.rate_limit:.1f} req/s, ~{minutes:.0f} min) ..."
        )
        validated_pairs, newly_correct = api_validate_pairs(heuristic_pairs, args.rate_limit)
        whitelist_words.extend(newly_correct)
        base_pairs = validated_pairs
    else:
        base_pairs = ss_pairs + ph_pairs

    # 5. Supplement laden (Getrenntschreibung, Sonstiges etc.)
    print("\nLade Supplement...")
    supplement = load_supplement()

    # 6. Zusammenfuehren: Supplement am Ende -> bei Dedup Vorrang
    all_pairs = base_pairs + supplement

    # 7. Schreiben
    print("\nSchreibe Ausgabe...")
    write_spellings(all_pairs)
    write_whitelist(whitelist_words)

    print("\nFertig.")
    print(f"  spellings.csv : {SPELLINGS_CSV}")
    print(f"  whitelist.csv : {WHITELIST_CSV}")


if __name__ == "__main__":
    main()
