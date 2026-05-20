# tools/spellings

Dieses Verzeichnis enthält die Wortlisten für die Altschreibungs-Prüfung
(`pdl_lt_dictconsistency/spelling.py`) sowie die Skripte zu ihrer Erzeugung.

## Dateien

| Datei | Inhalt |
|---|---|
| `spellings.csv` | Altschreibung → Neuschreibung (Spalten: `alt;neu`) |
| `whitelist.csv` | Wörter, die in neuer Rechtschreibung korrekt ß enthalten |
| `supplement.csv` | Manuell gepflegte Paare (Getrenntschreibung, Sonstiges) |
| `generate_spellings.py` | Erzeugt `spellings.csv` und `whitelist.csv` aus DWDS + Supplement |
| `dwds/` | DWDS-Lemmalisten (CSV, datiert; neueste wird automatisch verwendet) |
| `dwds/query_dwds_api.py` | Vollständige DWDS-API-Abfrage aller Lemmata (einmalig, lange Laufzeit) |
| `dwds/*-api.csv` | Ausgabe von `query_dwds_api.py` (Originalspalten + `lemma-neu`) |
| `dwds/dwds_api_errors.csv` | Fehlerdatei von `query_dwds_api.py` (persistiert über Läufe) |

## Wortlisten aktualisieren

```powershell
# Offline (nur DWDS-CSV + Supplement, keine Netzwerkverbindung nötig)
uv run python tools/spellings/generate_spellings.py

# Mit API-Liste (empfohlen; erst query_dwds_api.py vollständig ausführen)
uv run python tools/spellings/generate_spellings.py --list dwds/dwds_lemmata_2026-05-18-api.csv
```

Voraussetzung: eine aktuelle DWDS-Lemmaliste als CSV im Unterordner `dwds/`
(Dateiname beliebig, das Skript nimmt die alphabetisch neueste).
Die Liste ist abrufbar unter: https://www.dwds.de/d/dtb#lemmalist

## DWDS-Vollabfrage (`dwds/query_dwds_api.py`)

`generate_spellings.py` deckt nur ß/ss-, ph/f- und Dreifachkonsonant-Fälle
algorithmisch ab. Um weitere Altschreibungen zu finden (Vokaländerungen,
h-Wegfall, sonstige Einzelfälle), gibt es eine separate Vollabfrage aller
~260 000 DWDS-Lemmata per API.

**Laufzeit:** Bei 2 req/s ca. 36 Stunden. Der Lauf ist jederzeit unterbrechbar
und fortsetzbar – abgefragte Wörter werden übersprungen.

**Hinweis:** Nextcloud während der Abfrage pausieren, damit die temporäre
Ausgabedatei nicht gesperrt wird.

```powershell
# Erster Lauf (Standard: 2 req/s, Ausgabe in dwds/*-api.csv)
uv run python tools/spellings/dwds/query_dwds_api.py

# Schneller mit Pause alle 1000 Abfragen
uv run python tools/spellings/dwds/query_dwds_api.py --rate-limit 3 --pause-every 1000 --pause-seconds 30

# Fortsetzung nach Abbruch (Output-Datei existiert bereits -> wird als Basis genommen)
uv run python tools/spellings/dwds/query_dwds_api.py

# Alle Wörter erneut abfragen (z. B. nach DWDS-Update)
uv run python tools/spellings/dwds/query_dwds_api.py --requery

# Nur eine Teilmenge abfragen (Kandidaten-Index 0-basiert, Ende exklusiv)
uv run python tools/spellings/dwds/query_dwds_api.py --start 0 --end 50000
uv run python tools/spellings/dwds/query_dwds_api.py --start 50000 --end 100000
uv run python tools/spellings/dwds/query_dwds_api.py --start 100000
```

Die `--start`/`--end`-Indizes beziehen sich auf die gefilterte Kandidatenliste (nach Ausschluss
von Mehrwortausdrücken, Affixen, bereits abgefragten Wörtern). Bei parallelen Teilläufen
müssen die Ausgabe-Dateien unterschiedliche Namen haben.

### Ausgabespalte `lemma-neu`

| Wert | Bedeutung |
|---|---|
| (leer) | noch nicht abgefragt |
| gleich wie `lemma` | abgefragt, Schreibung korrekt |
| anderes Wort | Altschreibung → Neuform in `lemma-neu` |
| `NOT_FOUND` | Wort nicht in DWDS vorhanden |

### Fehlerbehandlung

Fehlgeschlagene Abfragen landen in `dwds/dwds_api_errors.csv`. Nach dem Hauptdurchlauf
werden sie automatisch erneut versucht. Nach 3 Fehlern (konfigurierbar mit
`--max-failures`) wird ein Wort dauerhaft übersprungen. Die Fehlerdatei bleibt
erhalten und wird beim nächsten Lauf eingelesen.

### Parameter

| Parameter | Standard | Beschreibung |
|---|---|---|
| `--input` | neueste `dwds/*.csv` | Eingabe-Lemmaliste |
| `--output` | `dwds/*-api.csv` | Ausgabe (mit `lemma-neu`) |
| `--errors` | `dwds/dwds_api_errors.csv` | Fehlerdatei |
| `--requery` | aus | Bereits abgefragte Wörter erneut abfragen |
| `--rate-limit` | 2.0 | Abfragen pro Sekunde |
| `--pause-every` | 0 | Reguläre Pause nach N Abfragen (0 = keine) |
| `--pause-seconds` | 5.0 | Dauer der regulären Pause |
| `--save-interval` | 10.0 | Speichern alle N Sekunden |
| `--max-failures` | 3 | Max. Fehler pro Wort vor dauerhaftem Überspringen |
| `--start` | 0 | Erster Kandidaten-Index (0-basiert, inklusiv) |
| `--end` | Ende | Letzter Kandidaten-Index (exklusiv) |

## Algorithmus (`generate_spellings.py`)

### ß → ss (`generate_ss_pairs`)

Für jedes DWDS-Lemma mit `ß`: Ersetze `ß` durch `ss`. Existiert die
ss-Form ebenfalls als DWDS-Lemma, handelt es sich um eine Altschreibung
(z. B. `Fluß` → `Fluss`). Existiert sie nicht, ist die ß-Form in neuer
Rechtschreibung korrekt (→ Whitelist, z. B. `Straße`, `Muße`).

### ph → f (`generate_ph_pairs`)

Analog: Für jedes DWDS-Lemma mit `ph`/`Ph`: Ersetze durch `f`/`F`.
Existiert die f-Form in DWDS → Altpaar (z. B. `Photographie` → `Fotografie`).
Wörter ohne f-Pendant bleiben unverändert (`Physik`, `Philosophie` usw.).

### Dreifachkonsonant (`generate_triple_pairs`)

Vor der Reform wurden drei gleiche Konsonanten an Wortgrenzen auf zwei
reduziert (z. B. `Brennessel` statt `Brennnessel`, `Schiffahrt` statt
`Schifffahrt`). Seit 1996 müssen alle drei geschrieben werden.

Für jedes DWDS-Lemma mit drei gleichen aufeinanderfolgenden Konsonanten
(`lll`, `nnn`, `fff`, `ttt` etc.): Entferne einen Konsonanten. Existiert die
Kurzform ebenfalls in DWDS → Altpaar. `s` wird ausgelassen (sss-Fälle entstehen
bereits durch ß→ss). Liefert ca. 168 Paare.

### Supplement

`supplement.csv` enthält Fälle, die kein Algorithmus abdeckt:
Getrenntschreibung (`soviel` → `so viel`), Vokaländerungen (`Gemse` → `Gämse`,
`Stengel` → `Stängel`), h-Wegfall (`rauh` → `rau`) u. a.
Supplement-Einträge haben bei Duplikaten Vorrang.

### API-Liste (`--list CSV`)

Mit `--list` werden Paare direkt aus einer per `query_dwds_api.py` erzeugten
CSV (Spalten `lemma` und `lemma-neu`) gebildet, statt die Heuristik zu verwenden.
Das ist autoritativer, da die Neuformen direkt aus DWDS stammen.

- `lemma-neu != lemma` → Altschreibungspaar
- `lemma-neu == lemma` → Schreibung korrekt; ß-Wörter kommen in Whitelist
- `lemma-neu` leer oder `NOT_FOUND` → Zeile wird übersprungen

### Ausschlüsse (`EXCLUDE_FROM_PAIRS`)

Einige Wörter erzeugen algorithmisch falsche Paare, weil ihr ss- bzw. f-Pendant
zufällig als anderes deutsches Wort in DWDS vorkommt. `EXCLUDE_FROM_PAIRS`
greift in beiden Modi (Heuristik und `--list`):

| Alt | Falsch generiertes Neu | Grund |
|---|---|---|
| `Maß` | `Mass` | `Mass` = Liter Bier; anderes Wort |
| `Phase` | `Fase` | `Fase` = Schrägkante; anderes Wort |
| `Phiale` | `Fiale` | `Fiale` = got. Türmchen; anderes Wort |

Neue Falschpaare können in `EXCLUDE_FROM_PAIRS` in `generate_spellings.py`
eingetragen werden.
