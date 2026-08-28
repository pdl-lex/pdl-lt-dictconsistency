// API-Referenz: dokumentiert die REST-Endpunkte (Daten-Ingest + Prüfungen)
// mit kopierbaren Beispielabfragen. Backend: pdl_lt_dictconsistency/api/.
import { useState, type CSSProperties, type ReactNode } from 'react'
import { Icon, type IconName } from '../design/icons'
import { useWorkbench, type LayoutMode } from '../state/workbench'

// Im Dev-Modus läuft die API auf Port 8000 (Vite proxyt nur /api, nicht /docs);
// in Produktion liefert FastAPI Frontend und API same-origin aus.
const BASE = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin

const card: CSSProperties = {
  background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-1)', padding: 14,
}

function Badge({ tone, children }: { tone: 'get' | 'post' | 'delete'; children: ReactNode }) {
  const colors = {
    get: { bg: 'var(--lt-info-soft)', fg: 'var(--lt-info)', line: 'var(--lt-info-line)' },
    post: { bg: 'var(--lt-primary-soft)', fg: 'var(--lt-primary)', line: 'var(--lt-primary-line)' },
    delete: { bg: 'var(--lt-err-soft)', fg: 'var(--lt-err)', line: 'var(--lt-err-line)' },
  }[tone]
  return (
    <span style={{
      fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em', fontFamily: 'var(--lt-font-mono)',
      padding: '2px 7px', borderRadius: 'var(--lt-r-xs)',
      background: colors.bg, color: colors.fg, border: `1px solid ${colors.line}`,
    }}>{children}</span>
  )
}

function Callout({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <div style={{
      display: 'flex', gap: 10, padding: '11px 13px', fontSize: 12.5, lineHeight: 1.55,
      background: 'var(--lt-primary-soft)', border: '1px solid var(--lt-primary-line)',
      borderRadius: 'var(--lt-r-md)', color: 'var(--lt-fg-1)',
    }}>
      <Icon name={icon} size={14} style={{ color: 'var(--lt-primary)', flexShrink: 0, marginTop: 2 }} />
      <div style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{children}</div>
    </div>
  )
}

function CodeBlock({ label, code }: { label?: string; code: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    void navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }
  return (
    <div style={{ minWidth: 0 }}>
      {label && (
        <div style={{
          fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase',
          color: 'var(--lt-fg-4)', fontFamily: 'var(--lt-font-mono)', margin: '0 0 4px',
        }}>{label}</div>
      )}
      <div style={{ position: 'relative' }}>
        <pre style={{
          margin: 0, padding: '10px 12px', background: 'var(--lt-bg-2)',
          border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-sm)',
          fontSize: 11.5, lineHeight: 1.55, fontFamily: 'var(--lt-font-mono)',
          color: 'var(--lt-fg-1)', overflowX: 'auto',
        }}>{code}</pre>
        <button onClick={copy} title="In Zwischenablage kopieren" style={{
          position: 'absolute', top: 6, right: 6, width: 24, height: 24,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-1)',
          borderRadius: 'var(--lt-r-sm)', color: copied ? 'var(--lt-primary)' : 'var(--lt-fg-3)',
          cursor: 'pointer',
        }}>
          <Icon name={copied ? 'check' : 'file'} size={11} />
        </button>
      </div>
    </div>
  )
}

function Endpoint({ method, path, children }: { method: 'GET' | 'POST' | 'DELETE'; path: string; children: ReactNode }) {
  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
        <Badge tone={method.toLowerCase() as 'get' | 'post' | 'delete'}>{method}</Badge>
        <code style={{ fontFamily: 'var(--lt-font-mono)', fontSize: 12.5, fontWeight: 600, color: 'var(--lt-fg-1)', wordBreak: 'break-all' }}>{path}</code>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 12.5, color: 'var(--lt-fg-2)', lineHeight: 1.55 }}>
        {children}
      </div>
    </div>
  )
}

const p0: CSSProperties = { margin: 0 }

export function ApiInfoConfig() {
  return (
    <div className="cfg-scroll" style={{ overflowY: 'auto', flex: 1, background: 'var(--lt-bg-2)', padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={card}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Schnittstelle</div>
        <div style={{ fontSize: 11.5, color: 'var(--lt-fg-3)', lineHeight: 1.7, fontFamily: 'var(--lt-font-mono)' }}>
          <div style={{ wordBreak: 'break-all' }}>Basis: {BASE}/api</div>
          <div>Format: JSON (Upload: multipart)</div>
          <div>Auth: Cookie-Session (POST /api/auth/login)</div>
        </div>
      </div>
      <div style={card}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Interaktive Dokumentation</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <GhostButton icon="book" onClick={() => window.open(`${BASE}/docs`, '_blank')}>Swagger UI (/docs)</GhostButton>
          <GhostButton icon="file" onClick={() => window.open(`${BASE}/openapi.json`, '_blank')}>OpenAPI-Schema (JSON)</GhostButton>
        </div>
      </div>
      <Callout icon="folder">
        Alle Prüfungen erwarten ein serverseitiges <code>directory</code> — entweder ein bekannter
        Server-Pfad, eine Datenquelle aus <code>GET /api/data/datasources</code> oder das Ergebnis
        eines Uploads (<code>POST /api/data/upload</code>).
      </Callout>
      <Callout icon="user">
        Alle Endpunkte außer <code>/api/auth/*</code> und <code>/api/health</code> verlangen eine
        angemeldete Session (Cookie <code>lt_session</code>, per <code>POST /api/auth/login</code>);
        ohne gültige Session antworten sie mit 401.
      </Callout>
    </div>
  )
}

function GhostButton({ icon, onClick, children }: { icon: IconName; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} style={{
      display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 10px',
      background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
      borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', fontSize: 12.5, cursor: 'pointer', textAlign: 'left',
    }}>
      <Icon name={icon} size={13} style={{ color: 'var(--lt-primary)' }} />
      {children}
    </button>
  )
}

/** Desktop-Konfigurator-Pane der API-Seite (analog ConfigPane). */
export function ApiInfoConfigPane({ layout }: { layout: LayoutMode }) {
  return (
    <section style={{
      gridArea: 'cfg', background: 'var(--lt-bg-0)',
      borderRight: layout === 'left' ? '1px solid var(--lt-line-1)' : 'none',
      borderLeft: layout === 'right' ? '1px solid var(--lt-line-1)' : 'none',
      borderBottom: layout === 'bottom' ? '1px solid var(--lt-line-1)' : 'none',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ padding: '14px 18px 12px', background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
        <div className="lt-eyebrow" style={{ marginBottom: 4 }}>Start</div>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>API</h2>
        <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12, lineHeight: 1.45 }}>
          REST-Zugriff auf alle Prüfungen — für Skripte und externe Systeme.
        </p>
      </div>
      <ApiInfoConfig />
    </section>
  )
}

export function ApiInfoMain() {
  const { directory } = useWorkbench()
  const dir = directory || '/pfad/zu/xml'

  const genericResponse = `{
  "results": [ { "…": "prüfungsspezifische Felder" } ],
  "files_checked": 3842,
  "result_count": 399,
  "duration_ms": 4170
}`

  return (
    <main className="agm-grid" style={{ gridArea: 'main', overflowY: 'auto', background: 'var(--lt-bg-1)', padding: '18px 20px' }}>
      <div style={{ maxWidth: 860, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div className="lt-eyebrow" style={{ marginBottom: 4 }}>Start</div>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>API-Referenz</h2>
          <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12.5, lineHeight: 1.5 }}>
            Alle Prüfungen dieser Oberfläche sind auch direkt per REST-API nutzbar.
          </p>
        </div>

        <Callout icon="bolt">
          Alle Endpunkte liegen unter <code>{BASE}/api</code>, Antworten sind JSON. Bis auf{' '}
          <code>/auth/*</code> und <code>/health</code> ist eine angemeldete Session nötig
          (Cookie <code>lt_session</code>, siehe <code>POST /api/auth/login</code> unten). Fehler
          kommen als HTTP-Status (401 = nicht angemeldet, 403 = Pfad außerhalb der erlaubten
          Datenwurzeln, 404 = Verzeichnis/Session unbekannt, 422 = ungültige Eingabe,
          500 = interner Fehler) mit Body <code>{'{"detail": "…"}'}</code>. Prüfungen antworten
          einheitlich mit:
          <div style={{ marginTop: 8 }}><CodeBlock code={genericResponse} /></div>
          Ausnahme: länger laufende Endpunkte (<code>/checks/references/run</code>,{' '}
          <code>/data/db-load</code>) starten nur einen Hintergrund-Job und antworten sofort (202)
          mit <code>job_id</code> — das obige Ergebnis kommt dann erst im{' '}
          <code>result</code>-Feld des zugehörigen Job-Status-Endpunkts.
        </Callout>

        <Endpoint method="POST" path="/api/auth/login">
          <p style={p0}>
            Anmelden. Setzt bei Erfolg das Session-Cookie <code>lt_session</code>{' '}
            (<code>HttpOnly</code>, 14 Tage gültig); alle weiteren Anfragen im selben Browser
            senden es automatisch mit.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/auth/login -c cookies.txt \\
  -H "Content-Type: application/json" \\
  -d '{"username": "…", "password": "…"}'`} />
        </Endpoint>

        <Endpoint method="GET" path="/api/auth/me">
          <p style={p0}>Angemeldeten Nutzer abfragen (Username, wbdb-Principal, Admin-Status).</p>
          <CodeBlock label="Anfrage" code={`curl ${BASE}/api/auth/me -b cookies.txt`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/auth/logout">
          <p style={p0}>Abmelden — löscht die Session serverseitig und das Cookie.</p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/auth/logout -b cookies.txt`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/data/scan">
          <p style={p0}>
            Serverseitiges XML-Verzeichnis scannen. Die zurückgegebene <code>directory</code> ist
            die Eingabe für alle Prüfungen; <code>files</code> listet die gefundenen XML-Dateien.
            Der Server kann Pfade auf konfigurierte Datenwurzeln beschränken — Pfade außerhalb
            (auch bei den Prüf-Endpunkten) werden mit 403 abgelehnt.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/data/scan \\
  -H "Content-Type: application/json" \\
  -d '{"directory": "${dir.replace(/\\/g, '/')}"}'`} />
          <CodeBlock label="Antwort" code={`{
  "directory": "${dir.replace(/\\/g, '/')}",
  "file_count": 3842,
  "files": [ { "subdir": "A", "filename": "Abriss.xml", "size_kb": 12.4 } ],
  "session_id": null,
  "errors": []
}`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/data/upload">
          <p style={p0}>
            XML- oder ZIP-Dateien hochladen (multipart/form-data, Feld <code>files</code>; ZIP wird
            entpackt, max. 50 MB pro Datei). Antwort wie bei <code>/scan</code>, zusätzlich mit
            {' '}<code>session_id</code>. Mit <code>?session_id=…</code> wird an eine bestehende
            Session angehängt; <code>DELETE /api/data/upload/{'{session_id}'}</code> räumt sie auf.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/data/upload \\
  -F "files=@woerterbuch.zip"`} />
        </Endpoint>

        <Endpoint method="GET" path="/api/data/datasources">
          <p style={p0}>
            Vorkonfigurierte Datensätze des Servers (<code>datasources.json</code>) mit Name,
            absolutem Pfad und Verfügbarkeit.
          </p>
          <CodeBlock label="Anfrage" code={`curl ${BASE}/api/data/datasources`} />
        </Endpoint>

        <Endpoint method="GET" path="/api/data/db-index/tree">
          <p style={p0}>
            wbdb-Artikelbaum aus dem lokalen Index-Cache (Ressource → Buchstabe → Artikel),
            gefiltert auf den wbdb-Principal des angemeldeten Nutzers; ohne zugeordneten Principal
            403, ohne aufgebauten Index 409 (ein Admin muss ihn per{' '}
            <code>POST /api/admin/wbdb-index/rebuild</code> anlegen). Weitere Endpunkte der
            gleichen Familie: <code>GET …/letter?resource_id=…&amp;letter=…</code> (Artikel eines
            Buchstabens, lazy beim Aufklappen), <code>GET …/search?q=…</code> (Lemma/Artikel-ID),
            {' '}<code>GET …/search-files?q=…&amp;resource_ids=…</code> (Dateiname, Artikelsuche)
            und <code>GET …/article?resource_id=…&amp;source_path=…</code> (Roh-XML eines
            einzelnen Artikels — live gegen wbdb, RLS-geprüft, nicht aus dem Cache).
          </p>
          <CodeBlock label="Anfrage" code={`curl ${BASE}/api/data/db-index/tree -b cookies.txt`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/data/db-load">
          <p style={p0}>
            Baum-Auswahl aus dem wbdb-Artikelbestand laden — ganze Ressourcen
            (<code>resource_ids</code>), Buchstaben (<code>resource_letters</code>, Paare aus
            Ressource + Buchstabe) oder einzelne Artikel (<code>articles</code>). Läuft live gegen
            wbdb (RLS-geprüft) als Hintergrund-Job: Antwort (202) enthält nur <code>job_id</code>;
            Fortschritt und Ergebnis (<code>directory</code> der geladenen Dateien, wie bei{' '}
            <code>/data/scan</code>) über <code>GET /api/data/db-load/{'{job_id}'}</code>, bis
            {' '}<code>status</code> "ok" oder "error" ist.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/data/db-load -b cookies.txt \\
  -H "Content-Type: application/json" \\
  -d '{"resource_letters": [["bwb", "A"]]}'`} />
          <CodeBlock label="Antwort (Job-Status)" code={`{
  "status": "ok", "done": 812, "total": 812, "error": null,
  "result": { "directory": "…", "file_count": 812, "files": [ "…" ] }
}`} />
        </Endpoint>

        <Endpoint method="GET" path="/api/data/file-content">
          <p style={p0}>
            Rohinhalt einer einzelnen bereits gescannten Datei (<code>directory</code>,{' '}
            <code>subdir</code>, <code>filename</code>) — für die Fundstellen-Vorschau in
            Ergebnistabellen. Unterliegt derselben Datenwurzeln-Prüfung wie <code>/data/scan</code>.
          </p>
          <CodeBlock label="Anfrage" code={`curl "${BASE}/api/data/file-content?directory=${dir.replace(/\\/g, '/')}&subdir=A&filename=Abriss.xml" -b cookies.txt`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/validator">
          <p style={p0}>
            XML-Validierung. <code>validation_type</code>: <code>"Wohlgeformtheit (Well-formed XML)"</code>
            {' '}oder <code>"TEI-Lex 0 Schema (RelaxNG)"</code>. Antwort enthält getrennte Listen
            {' '}<code>wellformed</code> und <code>schema_errors</code> (je Zeile: Datei, Zeile, Spalte, Fehler).
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/validator \\
  -H "Content-Type: application/json" \\
  -d '{
    "directory": "${dir.replace(/\\/g, '/')}",
    "validation_type": "Wohlgeformtheit (Well-formed XML)"
  }'`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/structure">
          <p style={p0}>
            Führt den XML-Baum aller ausgewählten Dateien zusammen: pro Pfad ein Knoten mit den
            vorkommenden Attributen (samt Beispielwerten) und Beispiel-Textinhalten. Optional auf
            eine einzelne Datei einschränkbar (<code>files</code>), um deren Inhalte im selben Baum
            zu markieren — Grundlage der Strukturanalyse-Seite in der Oberfläche.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/structure \\
  -H "Content-Type: application/json" \\
  -d '{"directory": "${dir.replace(/\\/g, '/')}"}'`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/pathfinder">
          <p style={p0}>
            Tag- und Pfadsuche. <code>user_input</code> ist ein Tag (<code>bedeutung</code>), ein Pfad
            (<code>sense/sense</code>) oder ein Wildcard-Muster (<code>sense/*/bibl</code>).
            Treffer: XPath (<code>full_path</code>), Inhalt (<code>text_content</code>), Datei, Zeile.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/pathfinder \\
  -H "Content-Type: application/json" \\
  -d '{"directory": "${dir.replace(/\\/g, '/')}", "user_input": "sense/*/bibl"}'`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/uniqueness">
          <p style={p0}>
            Einmaligkeitsprüfung je Dokument. <code>mode</code>: <code>Tag</code> · <code>Tag-Inhalt</code> ·
            {' '}<code>Tag &amp; Attribut</code> · <code>Attribut</code>; dazu <code>tag_name</code> bzw.
            {' '}<code>attribute_name</code> (auch <code>xml:id</code>).
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/uniqueness \\
  -H "Content-Type: application/json" \\
  -d '{
    "directory": "${dir.replace(/\\/g, '/')}",
    "mode": "Tag & Attribut",
    "tag_name": "artikel",
    "attribute_name": "xml:id"
  }'`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/nesting">
          <p style={p0}>
            Verschachtelungsanalyse. <code>search_mode</code>: <code>Direkte Verschachtelung</code> ·
            {' '}<code>Beliebige Verschachtelung</code> (jeweils mit <code>tag_input</code>) ·
            {' '}<code>Pfad / Wildcard</code> (mit <code>path_input</code>, z. B. <code>sense/*/form</code>).
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/nesting \\
  -H "Content-Type: application/json" \\
  -d '{
    "directory": "${dir.replace(/\\/g, '/')}",
    "search_mode": "Direkte Verschachtelung",
    "tag_input": "sense"
  }'`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/senses-stats">
          <p style={p0}>
            Anzahl und Textlänge (min/max/Ø) eines Tags je Datei, z. B. für <code>sense</code>.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/senses-stats \\
  -H "Content-Type: application/json" \\
  -d '{"directory": "${dir.replace(/\\/g, '/')}", "tag_name": "sense"}'`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/tag-content/search">
          <p style={p0}>
            Tag-Inhalte durchsuchen bzw. nicht-leere Tags finden. <code>tags_to_search</code> ist
            Pflicht; <code>search_text</code> leer = alle nicht-leeren Treffer;
            optional <code>attrs_to_filter</code>/<code>attr_value</code>. Die Hilfsendpunkte
            {' '}<code>POST …/tags</code>, <code>POST …/attrs</code> und <code>POST …/attr-values</code>
            {' '}liefern die in den Daten vorkommenden Tags, Attribute und Attributwerte.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/tag-content/search \\
  -H "Content-Type: application/json" \\
  -d '{
    "directory": "${dir.replace(/\\/g, '/')}",
    "tags_to_search": ["bedeutung"],
    "search_text": "",
    "include_whitespace": true
  }'`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/references/run">
          <p style={p0}>
            Verweisprüfung starten (BDO-Artikelreferenzen live gegen wbdb und/oder http(s)-Links
            per echtem Request). Läuft als zweiphasiger Hintergrund-Job (erst Fundstellen-Scan,
            dann Zielprüfung) — Antwort (202) enthält nur <code>job_id</code>. <code>sources</code>{' '}
            ist eine Liste aus <code>tag</code> (leer = beliebiger Tag) + <code>attribute</code>;
            {' '}<code>check_http_links</code> prüft zusätzlich alle http(s)-Links in Text und
            Attributen; <code>include_fehlt_marked</code> schließt bereits als fehlend markierte
            Verweise (<code>@fehlt="ja"</code>) mit ein. Fortschritt/Ergebnis über{' '}
            <code>GET /api/checks/references/run/{'{job_id}'}</code>, bis <code>status</code> "ok"
            oder "error" ist (<code>phase</code>: "scanning" oder "checking"); die Ergebnisliste
            enthält nur kaputte Verweise.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/references/run -b cookies.txt \\
  -H "Content-Type: application/json" \\
  -d '{
    "directory": "${dir.replace(/\\/g, '/')}",
    "sources": [{"tag": "verweis", "attribute": "ziel"}],
    "check_http_links": false,
    "include_fehlt_marked": true
  }'`} />
          <CodeBlock label="Antwort (Job-Status)" code={`{
  "status": "ok", "phase": "checking", "done": 1204, "total": 1204, "error": null,
  "result": { "results": [ "…" ], "files_checked": 3842, "result_count": 17, "duration_ms": 15230 }
}`} />
        </Endpoint>

        <Endpoint method="POST" path="/api/checks/spelling/search">
          <p style={p0}>
            Alte (Reform-)Schreibungen in Textinhalten finden. <code>included_tags</code> ist Pflicht
            (Vorschläge: <code>POST /api/checks/spelling/tags</code>); eigene Wortpaare über
            {' '}<code>custom_spellings</code> mit <code>custom_list_mode</code> <code>extend</code> |
            {' '}<code>replace</code>. Die integrierte Wortliste liefert
            {' '}<code>GET /api/checks/spelling/wordlist</code>.
          </p>
          <CodeBlock label="Anfrage" code={`curl -X POST ${BASE}/api/checks/spelling/search \\
  -H "Content-Type: application/json" \\
  -d '{
    "directory": "${dir.replace(/\\/g, '/')}",
    "included_tags": ["bedeutung", "etymologie"],
    "custom_spellings": [{"alt": "daß", "neu": "dass"}],
    "custom_list_mode": "extend"
  }'`} />
          <CodeBlock label="Antwort (results-Zeile)" code={`{
  "quelle": "BWB Bd. 2, H. 13", "subdir": "A", "filename": "Abriss.xml",
  "line": 41, "tag": "bedeutung",
  "gefunden": "daß", "vorschlag": "dass",
  "kontext": "…so daß der Abriß…"
}`} />
        </Endpoint>

        <Endpoint method="GET" path="/api/health">
          <p style={p0}>Liveness-Check, antwortet mit <code>{'{"status": "ok"}'}</code>.</p>
          <CodeBlock label="Anfrage" code={`curl ${BASE}/api/health`} />
        </Endpoint>
      </div>
    </main>
  )
}
