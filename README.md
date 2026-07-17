# pdl-lt-dictconsistency

Konsistenzprüfung für XML-Wörterbücher (BAdW · Plattform für Digitale
Lexikographie). Python-Backend (FastAPI + lxml) mit React/Vite-Frontend;
alle Prüfungen sind zusätzlich als REST-API unter `/api` von außen nutzbar
(interaktive Doku unter `/docs`, Übersicht im Frontend unter „Start › API").

## Prüfungen

- **Validator** — Wohlgeformtheit oder TEI-Lex-0-Schema (RelaxNG)
- **Tag- und Pfadsuche** — Tags/Pfade inkl. Wildcards (`sense/*/bibl`)
- **Einmaligkeit** — Tags, Inhalte oder Attribute je Dokument einmalig?
- **Verschachtelung** — Verschachtelungstiefe und Pfad-Muster
- **Inhalt / Leere Tags** — Textinhalte und Attribute durchsuchen
- **Anzahl und Länge** — Statistik (min/max/Ø) je Tag und Datei
- **Alte Rechtschreibung** — Reformschreibungen vor 1996/2006 finden

## Entwicklung

```powershell
# Backend (Port 8000, Docs unter /docs)
uv run uvicorn pdl_lt_dictconsistency.api.main:app --reload

# Frontend (Port 5173, proxyt /api -> :8000)
cd frontend; npm install; npm run dev
```

## Produktion

```powershell
docker build -t dictconsistency .
docker run -p 8000:8000 dictconsistency
```

Das mehrstufige Dockerfile baut `frontend/dist` und liefert Frontend (`/`)
und API (`/api`) gemeinsam über uvicorn auf Port 8000 aus. Vorkonfigurierte
Datensätze über `datasources.json` (Vorlage: `datasources.example.json`).

Im Container ist `LT_DATA_ROOTS=/mnt/data/wb/data` gesetzt: Scan- und
Prüf-Endpunkte akzeptieren nur Verzeichnisse unterhalb dieser Wurzel(n)
sowie Upload-Sessions (403 sonst). Mehrere Wurzeln sind per `:` trennbar
(`docker run -e LT_DATA_ROOTS=/a:/b …`); ohne die Variable — z. B. in der
lokalen Entwicklung — gibt es keine Beschränkung.
