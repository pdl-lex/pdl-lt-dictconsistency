"""
generate_spellings.py

Erzeugt spellings.csv (alt->neu-Paare) und whitelist.csv (korrekte ß-Woerter)
aus der DWDS-Lemmaliste (tools/spellings/dwds/*.csv) plus supplement.csv
(manuell gepflegte Eintraege fuer Getrenntschreibung, Sonstiges etc.).

Algorithmus fuer ß->ss (Heuristik, Standard):
  Fuer jedes Lemma aus DWDS das 'ß' enthaelt: Ersetze 'ß' durch 'ss'.
  Existiert die ss-Form ebenfalls in DWDS -> Altschreibung (Paar).
  Existiert sie nicht -> ß-Schreibung korrekt (Whitelist).

Algorithmus fuer ph->f (Heuristik, Standard):
  Fuer jedes Lemma aus DWDS das 'ph' enthaelt: Ersetze 'ph' durch 'f'.
  Existiert die f-Form ebenfalls in DWDS -> Altschreibung (Paar).
  Existiert sie nicht -> ph-Schreibung bleibt (Physik, Philosophie etc.).

Whitelist:
  Alle DWDS-Lemmata mit 'ß', fuer die keine ss-Version in DWDS existiert.

API-Liste (--list CSV):
  Statt Heuristik: Paare direkt aus einer per query_dwds_api.py erzeugten
  CSV mit den Spalten 'lemma' und 'lemma-neu' bilden.
  Paar:      lemma-neu != lemma, nicht leer, nicht NOT_FOUND
  Whitelist: ß-Woerter wo lemma-neu == lemma (korrekte Schreibung bestaetigt)

Verwendung:
  uv run python tools/spellings/generate_spellings.py
  uv run python tools/spellings/generate_spellings.py --list dwds/dwds_lemmata_2026-05-18-api.csv

Abhaengigkeiten: keine externen (nur stdlib)
"""

import argparse
import csv
import re
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


def generate_triple_pairs(dwds_words: set[str]) -> list[tuple[str, str]]:
    """
    Erzeugt alt->neu-Paare für Dreifachkonsonanten aus der DWDS-Lemmaliste.

    Vor der Reform wurden drei gleiche Konsonanten an Wortgrenzen auf zwei
    reduziert (Brennessel statt Brennnessel, Schiffahrt statt Schifffahrt).
    Seit 1996 müssen alle drei geschrieben werden.

    Für jedes DWDS-Lemma mit drei gleichen aufeinanderfolgenden Konsonanten:
    Entferne einen Konsonanten. Existiert die Kurzform ebenfalls in DWDS
    -> Altschreibungspaar.

    's' wird ausgelassen: sss-Fälle entstehen bereits durch ß->ss (z. B.
    Ablaßschleuse -> Ablassschleuse) und sind dort schon erfasst.
    """
    pairs: list[tuple[str, str]] = []
    _triple = re.compile(r"([bcdfgklmnprt])\1\1", re.IGNORECASE)
    seen: set[tuple[str, str]] = set()

    for word in sorted(dwds_words):
        m = _triple.search(word)
        if not m:
            continue
        # Entferne den ersten der drei gleichen Konsonanten -> Altform
        pos = m.start()
        short_form = word[:pos] + word[pos + 1:]
        if short_form in dwds_words:
            pair = (short_form, word)
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)

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


# ── API-Liste ──────────────────────────────────────────────────────────────


def load_api_list(path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Laedt API-Ergebnisliste (Spalten: lemma, lemma-neu) und bildet Paare/Whitelist.

    Paar:      lemma-neu != lemma, nicht leer, nicht NOT_FOUND
    Whitelist: ß-Woerter wo lemma-neu == lemma (korrekte Schreibung bestaetigt)
    Zeilen mit leerem lemma-neu (noch nicht abgefragt) werden uebersprungen.
    """
    pairs: list[tuple[str, str]] = []
    whitelist: list[str] = []

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lemma = (row.get("lemma") or "").strip()
            lemma_neu = (row.get("lemma-neu") or "").strip()
            if not lemma or not lemma_neu or lemma_neu == "NOT_FOUND":
                continue
            if lemma in EXCLUDE_FROM_PAIRS:
                if "ß" in lemma:
                    whitelist.append(lemma)
                continue
            if lemma_neu == lemma:
                if "ß" in lemma:
                    whitelist.append(lemma)
            else:
                pairs.append((lemma, lemma_neu))

    return pairs, whitelist


# ── Hauptprogramm ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Erzeugt spellings.csv und whitelist.csv aus DWDS-Lemmaliste."
    )
    parser.add_argument(
        "--list",
        metavar="CSV",
        help="API-Ergebnisliste mit lemma/lemma-neu Spalten (aus query_dwds_api.py) "
             "statt Heuristik verwenden.",
    )
    args = parser.parse_args()

    print("=== generate_spellings.py ===\n")

    if args.list:
        # Paare direkt aus API-Liste
        list_path = Path(args.list)
        if not list_path.is_absolute():
            list_path = HERE / list_path
        print(f"Lade API-Liste: {list_path.name} ...")
        base_pairs, whitelist_words = load_api_list(list_path)
        print(f"  {len(base_pairs)} Paare, {len(whitelist_words)} Whitelist-Eintraege.")
    else:
        # Heuristik
        print("Lade DWDS-Lemmaliste...")
        dwds_words = load_dwds()

        print("\nErzeuge ß/ss-Paare aus DWDS...")
        ss_pairs, whitelist_words = generate_ss_pairs(dwds_words)
        print(f"  {len(ss_pairs)} Paare, {len(whitelist_words)} Whitelist-Eintraege.")

        print("\nErzeuge ph->f-Paare aus DWDS...")
        ph_pairs = generate_ph_pairs(dwds_words)
        print(f"  {len(ph_pairs)} Paare.")

        print("\nErzeuge Dreifachkonsonanten-Paare aus DWDS...")
        triple_pairs = generate_triple_pairs(dwds_words)
        print(f"  {len(triple_pairs)} Paare.")

        base_pairs = ss_pairs + ph_pairs + triple_pairs

    # Supplement laden (Getrenntschreibung, Sonstiges etc.)
    print("\nLade Supplement...")
    supplement = load_supplement()

    # Zusammenfuehren: Supplement am Ende -> bei Dedup Vorrang
    all_pairs = base_pairs + supplement

    # Schreiben
    print("\nSchreibe Ausgabe...")
    write_spellings(all_pairs)
    write_whitelist(whitelist_words)

    print("\nFertig.")
    print(f"  spellings.csv : {SPELLINGS_CSV}")
    print(f"  whitelist.csv : {WHITELIST_CSV}")


if __name__ == "__main__":
    main()
