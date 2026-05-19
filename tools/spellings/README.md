# tools/spellings

Dieses Verzeichnis enthält die Wortlisten für die Altschreibungs-Prüfung
(`pdl_lt_dictconsistency/spelling.py`) sowie das Skript zu ihrer Erzeugung.

## Dateien

| Datei | Inhalt |
|---|---|
| `spellings.csv` | Altschreibung → Neuschreibung (Spalten: `alt;neu`) |
| `whitelist.csv` | Wörter, die in neuer Rechtschreibung korrekt ß enthalten |
| `supplement.csv` | Manuell gepflegte Paare (Getrenntschreibung, Sonstiges) |
| `generate_spellings.py` | Erzeugt `spellings.csv` und `whitelist.csv` aus DWDS + Supplement |
| `dwds/` | DWDS-Lemmalisten (CSV, datiert; neueste wird automatisch verwendet) |

## Wortlisten aktualisieren

```powershell
# Offline (nur DWDS-CSV + Supplement, keine Netzwerkverbindung nötig)
uv run python tools/spellings/generate_spellings.py

# Mit API-Validierung (empfohlen, braucht Internetverbindung)
uv run python tools/spellings/generate_spellings.py --api

# Mit höherer Anfragerate (Anfragen pro Sekunde, Standard: 2)
uv run python tools/spellings/generate_spellings.py --api --rate-limit 5
```

Voraussetzung: eine aktuelle DWDS-Lemmaliste als CSV im Unterordner `dwds/`
(Dateiname beliebig, das Skript nimmt die alphabetisch neueste).
Die Liste ist abrufbar unter: https://www.dwds.de/d/dtb#lemmalist

## Algorithmus

### ß → ss (`generate_ss_pairs`)

Für jedes DWDS-Lemma mit `ß`: Ersetze `ß` durch `ss`. Existiert die
ss-Form ebenfalls als DWDS-Lemma, handelt es sich um eine Altschreibung
(z. B. `Fluß` → `Fluss`). Existiert sie nicht, ist die ß-Form in neuer
Rechtschreibung korrekt (→ Whitelist, z. B. `Straße`, `Muße`).

### ph → f (`generate_ph_pairs`)

Analog: Für jedes DWDS-Lemma mit `ph`/`Ph`: Ersetze durch `f`/`F`.
Existiert die f-Form in DWDS → Altpaar (z. B. `Photographie` → `Fotografie`).
Wörter ohne f-Pendant bleiben unverändert (`Physik`, `Philosophie` usw.).

### Supplement

`supplement.csv` enthält Fälle, die der Algorithmus nicht abdeckt:
Getrenntschreibung (`soviel` → `so viel`), Sonstiges (`Stengel` → `Stängel`).
Supplement-Einträge haben bei Duplikaten Vorrang.

### API-Validierung (`--api`)

Mit `--api` werden die algorithmisch ermittelten Kandidatenpaare per
DWDS-API (`/api/wb/snippet/`) verifiziert. Die API gibt für jedes Wort die
kanonische Schreibung zurück:

- `input == lemma` → Wort ist korrekt geschrieben (kein Paar; ß-Wörter → Whitelist)
- `input != lemma` → Altschreibung bestätigt, `lemma` als Neuform übernommen

`--rate-limit REQ/S` steuert die Anfragen pro Sekunde (Standard: 2, d. h.
0,5 s Pause zwischen Anfragen). Bei ~4400 Paaren dauert die Validierung
damit ca. 37 Minuten, bei `--rate-limit 5` ca. 15 Minuten.

Schlägt eine API-Anfrage fehl, wird das heuristisch ermittelte Paar als
Fallback beibehalten.

### Ausschlüsse (`EXCLUDE_FROM_PAIRS`)

Im Offline-Modus (ohne `--api`) erzeugen einige Wörter algorithmisch falsche
Paare, weil ihr ss- bzw. f-Pendant zufällig als anderes deutsches Wort in
DWDS vorkommt. Mit `--api` werden diese Fälle automatisch erkannt (API gibt
`input == lemma` zurück). Im Offline-Modus greift `EXCLUDE_FROM_PAIRS`:

| Alt | Falsch generiertes Neu | Grund |
|---|---|---|
| `Maß` | `Mass` | `Mass` = Liter Bier; anderes Wort |
| `Phase` | `Fase` | `Fase` = Schrägkante; anderes Wort |
| `Phiale` | `Fiale` | `Fiale` = got. Türmchen; anderes Wort |

Neue Falschpaare können in `EXCLUDE_FROM_PAIRS` in `generate_spellings.py`
eingetragen werden.
