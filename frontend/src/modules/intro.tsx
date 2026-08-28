// Einführungsseite: Landing-/Startseite mit Kurzbeschreibung des Werkzeugs
// und einer Übersicht aller Prüfungen. In der früheren Reflex-App (v1) war
// dies die Startseite (pdl_lt_dictconsistency.py::index). Wie „API"
// (apiInfo.tsx) und „Strukturanalyse" (structure.tsx) eine Sonderseite ohne
// Tabellen-Ergebnis, siehe App.tsx: isIntro.
import type { CSSProperties, ReactNode } from 'react'
import { Icon, type IconName } from '../design/icons'
import { useWorkbench, type LayoutMode } from '../state/workbench'

const card: CSSProperties = {
  background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-1)', padding: 14,
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

interface CheckEntry { label: string; group: string; description: string; id?: string; planned?: boolean }

const CHECKS: CheckEntry[] = [
  { label: 'Daten', group: 'Start', id: 'data',
    description: 'Daten aus einem Server-Verzeichnis laden, XML-/ZIP-Dateien hochladen, oder eine vorkonfigurierte Datenquelle wählen.' },
  { label: 'API', group: 'Start', id: 'api',
    description: 'Referenz aller REST-Endpunkte (Daten-Ingest + Prüfungen) mit kopierbaren Beispielabfragen.' },
  { label: 'Artikelsuche', group: 'Start', id: 'artikelsuche',
    description: 'Freitextsuche über den Dateinamen im wbdb-Artikelbestand, mit Anzeige des gefundenen Artikels als Roh-XML.' },
  { label: 'XML/TL0 Validator', group: 'XML', id: 'validator',
    description: 'Prüfung auf XML-Wohlgeformtheit und TEI-Lex 0 Konformität.' },
  { label: 'Strukturanalyse', group: 'XML', id: 'structure',
    description: 'Führt den XML-Baum aller Dateien eines Verzeichnisses zusammen, zeigt Tags, Attribute und Textbeispiele und erlaubt die Projektion einzelner Dateien in den Gesamtbaum.' },
  { label: 'Tag- und Pfadsuche', group: 'XML', id: 'pathfinder',
    description: 'Suche nach bestimmten Tags oder Pfaden im XML-Baum, inklusive Wildcards.' },
  { label: 'Inhalt / Leere Tags', group: 'XML', id: 'content',
    description: 'Suche nach Textinhalten, leeren Tags und Umbrüchen.' },
  { label: 'Einmaligkeit', group: 'XML', id: 'unique',
    description: 'Prüft, ob Tags oder Attribute innerhalb eines Dokuments mehrfach vorkommen.' },
  { label: 'Verschachtelung', group: 'XML', id: 'nesting',
    description: 'Analysiert Verschachtelung und Verschachtelungstiefe von Tags.' },
  { label: 'Verweise', group: 'XML', id: 'references',
    description: 'Prüft Verweise (BDO-Artikelreferenzen gegen die Datenbank und/oder http(s)-Links) auf Erreichbarkeit ihres Ziels.' },
  { label: 'Anzahl und Länge', group: 'Stil und Schreibung', id: 'stats',
    description: 'Bedeutungsangaben (o. ä.) werden hinsichtlich ihrer Anzahl sowie minimaler und maximaler Länge ausgewertet.' },
  { label: 'Alte Rechtschreibung', group: 'Stil und Schreibung', id: 'spelling',
    description: 'Beliebige Tags können auf alte Rechtschreibung geprüft werden. Ausgegeben wird eine Liste falsch geschriebener Wörter mit Korrekturvorschlägen sowie Vereinheitlichungsvorschlägen (DWDS als Referenz) bei mehreren erlaubten Schreibweisen.' },
  { label: 'LLM-Anfrage', group: 'LLM', planned: true,
    description: 'Einzelne oder mehrere XML-Dateien an ein lokales oder Cloud-LLM senden; per Chat Fragen stellen und Analysen vornehmen. Noch nicht auf die neue Oberfläche portiert.' },
  { label: 'Texterkennung (OCR)', group: 'LLM', planned: true,
    description: 'Texterkennung für gescannte Vorlagen. Noch nicht auf die neue Oberfläche portiert.' },
]

const GROUP_ORDER = ['Start', 'XML', 'Stil und Schreibung', 'LLM']

function CheckCard({ entry, onOpen }: { entry: CheckEntry; onOpen: (id: string) => void }) {
  const clickable = !!entry.id
  return (
    <div style={{
      ...card, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6,
      cursor: clickable ? 'pointer' : 'default', opacity: entry.planned ? 0.65 : 1,
    }} onClick={() => entry.id && onOpen(entry.id)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          fontSize: 10.5, fontWeight: 700, letterSpacing: '0.02em', padding: '2px 8px',
          borderRadius: 'var(--lt-r-xs)', background: entry.planned ? 'var(--lt-bg-2)' : 'var(--lt-primary-soft)',
          color: entry.planned ? 'var(--lt-fg-3)' : 'var(--lt-primary)',
          border: `1px solid ${entry.planned ? 'var(--lt-line-1)' : 'var(--lt-primary-line)'}`,
        }}>{entry.label}</span>
        {entry.planned && <span style={{ fontSize: 10.5, color: 'var(--lt-fg-4)' }}>in Vorbereitung</span>}
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--lt-fg-2)', lineHeight: 1.5 }}>{entry.description}</div>
    </div>
  )
}

export function IntroConfig() {
  const { setActiveId, setDataDialogOpen } = useWorkbench()
  return (
    <div className="cfg-scroll" style={{ overflowY: 'auto', flex: 1, background: 'var(--lt-bg-2)', padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={card}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Erste Schritte</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <GhostButton icon="folder" onClick={() => setDataDialogOpen(true)}>Daten wählen…</GhostButton>
          <GhostButton icon="layers" onClick={() => setActiveId('validator')}>XML-Validator öffnen</GhostButton>
          <GhostButton icon="bolt" onClick={() => setActiveId('api')}>API-Referenz öffnen</GhostButton>
        </div>
      </div>
      <Callout icon="folder">
        Jede Prüfung braucht ein Datenverzeichnis. Über die Karte „Daten wählen…" lässt sich ein
        Verzeichnis-Pfad angeben, XML/ZIP hochladen oder eine Datenbank-Ressource laden.
      </Callout>
    </div>
  )
}

export function IntroConfigPane({ layout }: { layout: LayoutMode }) {
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
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Einführung</h2>
        <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12, lineHeight: 1.45 }}>
          Überblick über alle verfügbaren Prüfungen.
        </p>
      </div>
      <IntroConfig />
    </section>
  )
}

export function IntroMain() {
  const { setActiveId } = useWorkbench()
  return (
    <main className="agm-grid" style={{ gridArea: 'main', overflowY: 'auto', background: 'var(--lt-bg-1)', padding: '18px 20px' }}>
      <div style={{ maxWidth: 860, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div className="lt-eyebrow" style={{ marginBottom: 4 }}>Start</div>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Willkommen</h2>
          <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12.5, lineHeight: 1.55 }}>
            Dieses Werkzeug bietet verschiedene Möglichkeiten zur Konsistenzprüfung von
            Wörterbüchern auf XML-Basis. Es funktioniert mit beliebigen XML-Schemata, am besten
            jedoch mit TEI-Lex 0.
          </p>
        </div>

        {GROUP_ORDER.map((group) => {
          const entries = CHECKS.filter((c) => c.group === group)
          if (entries.length === 0) return null
          return (
            <div key={group}>
              <div className="lt-eyebrow" style={{ marginBottom: 8 }}>{group}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 10 }}>
                {entries.map((entry) => <CheckCard key={entry.label} entry={entry} onOpen={setActiveId} />)}
              </div>
            </div>
          )
        })}
      </div>
    </main>
  )
}
