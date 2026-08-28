// Artikelsuche: Freitextsuche über den Dateinamen (source_path) im lokalen
// wbdb-Index-Cache, gefiltert auf ausgewählte Wörterbücher, mit Anzeige des
// gefundenen Artikels als Roh-XML. Anders als die tabellarischen Prüfungen
// (registry.ts) braucht das kein Datenverzeichnis (`directory`) — es fragt
// direkt gegen wbdb (wie der "Datenbank"-Tab im Daten-Dialog, siehe
// layout/DbTree.tsx) — daher Sonderseite neben ConfigPane/ResultsPane, wie
// „Strukturanalyse" (modules/structure.tsx; siehe App.tsx: isArtikelsuche).
// Backend: GET /api/data/db-index/search-files, GET /api/data/db-index/article
// (pdl_lt_dictconsistency/api/routers/db_index.py).
import {
  createContext, useContext, useEffect, useMemo, useRef, useState,
  type CSSProperties, type ReactNode,
} from 'react'
import { Icon } from '../design/icons'
import { useIsMobile } from '../design/useIsMobile'
import { ApiError, dataApi, type DbResourceSummary, type DbSearchHit } from '../api/client'
import type { LayoutMode } from '../state/workbench'

// ============ Context ============

interface ArtikelsucheState {
  tree: DbResourceSummary[] | null
  treeError: string
  notBuilt: boolean
  ensureTree: () => void
  selectedResources: Set<string>
  toggleResource: (id: string) => void
  clearResources: () => void
  query: string
  setQuery: (q: string) => void
  results: DbSearchHit[]
  searching: boolean
  searchError: string
  selected: DbSearchHit | null
  select: (hit: DbSearchHit) => void
  content: string | null
  contentLoading: boolean
  contentError: string
}

const Ctx = createContext<ArtikelsucheState | null>(null)

export function ArtikelsucheProvider({ children }: { children: ReactNode }) {
  const [tree, setTree] = useState<DbResourceSummary[] | null>(null)
  const [treeError, setTreeError] = useState('')
  const [notBuilt, setNotBuilt] = useState(false)
  const [selectedResources, setSelectedResources] = useState<Set<string>>(new Set())

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<DbSearchHit[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [selected, setSelected] = useState<DbSearchHit | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [contentLoading, setContentLoading] = useState(false)
  const [contentError, setContentError] = useState('')

  // Lazy statt beim Provider-Mount: der Provider umschließt die ganze
  // Workbench (analog StructureProvider), damit die Suche beim Seitenwechsel
  // erhalten bleibt — der Baum-Abruf (live gegen wbdb, siehe
  // wbdb/index_store.py::_current_scope) soll aber nur laufen, wenn die Seite
  // tatsächlich geöffnet wird, nicht bei jedem App-Start.
  const treeRequested = useRef(false)
  const ensureTree = () => {
    if (treeRequested.current) return
    treeRequested.current = true
    dataApi.dbIndexTree()
      .then(setTree)
      .catch((e) => { if (e instanceof ApiError && e.status === 409) setNotBuilt(true); else setTreeError(String(e)) })
  }

  // Zähler statt nur des Timeout-Handles: der Debounce verhindert zwar
  // überlappende *geplante* Anfragen, aber eine bereits abgeschickte Anfrage
  // (z. B. für "d") kann noch unterwegs sein, wenn eine spätere (für
  // "datschi") schon fertig ist — ohne Reihenfolge-Absicherung würde die
  // veraltete Antwort das korrekte Ergebnis überschreiben.
  const searchSeq = useRef(0)
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    const q = query.trim()
    if (!q) { searchSeq.current += 1; setResults([]); setSearchError(''); setSearching(false); return }
    setSearching(true)
    searchTimer.current = setTimeout(() => {
      const seq = ++searchSeq.current
      dataApi.dbIndexSearchFiles(q, [...selectedResources])
        .then((hits) => { if (seq === searchSeq.current) { setResults(hits); setSearchError('') } })
        .catch((e) => { if (seq === searchSeq.current) setSearchError(String(e)) })
        .finally(() => { if (seq === searchSeq.current) setSearching(false) })
    }, 250)
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current) }
  }, [query, selectedResources])

  const toggleResource = (id: string) => {
    setSelectedResources((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  const clearResources = () => setSelectedResources(new Set())

  const select = (hit: DbSearchHit) => {
    setSelected(hit)
    setContent(null)
    setContentError('')
    setContentLoading(true)
    dataApi.dbIndexArticle(hit.resource_id, hit.source_path)
      .then((r) => setContent(r.content))
      .catch((e) => setContentError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setContentLoading(false))
  }

  const value = useMemo<ArtikelsucheState>(() => ({
    tree, treeError, notBuilt, ensureTree, selectedResources, toggleResource, clearResources,
    query, setQuery, results, searching, searchError, selected, select,
    content, contentLoading, contentError,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [tree, treeError, notBuilt, selectedResources, query, results, searching, searchError, selected, content, contentLoading, contentError])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useArtikelsuche(): ArtikelsucheState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useArtikelsuche must be used within ArtikelsucheProvider')
  return v
}

// ============ Shared styles ============

const card: CSSProperties = {
  background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-1)', padding: 14,
}

// ============ Config pane (Suche + Wörterbuch-Multiselect) ============

export function ArtikelsucheConfig() {
  const { tree, treeError, notBuilt, ensureTree, selectedResources, toggleResource, clearResources, query, setQuery } = useArtikelsuche()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { ensureTree() }, [])
  return (
    <div className="cfg-scroll" style={{ overflowY: 'auto', flex: 1, background: 'var(--lt-bg-2)', padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={card}>
        <div style={{ fontSize: 12, color: 'var(--lt-fg-3)', lineHeight: 1.5, marginBottom: 10 }}>
          Sucht im Dateinamen der Artikel im schnellen lokalen Index — kein Datenverzeichnis nötig.
        </div>
        <div style={{ position: 'relative' }}>
          <Icon name="search" size={12} style={{ position: 'absolute', left: 9, top: 10, color: 'var(--lt-fg-4)' }} />
          <input
            value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Dateiname durchsuchen…" autoFocus
            style={{
              width: '100%', boxSizing: 'border-box', padding: '8px 10px 8px 28px', fontSize: 13,
              background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
              borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', outline: 'none',
            }}
          />
        </div>
      </div>

      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
          <span className="lt-eyebrow" style={{ flex: 1 }}>Wörterbücher</span>
          {selectedResources.size > 0 && (
            <button onClick={clearResources} style={{
              fontSize: 11, color: 'var(--lt-fg-3)', background: 'none', border: '1px solid var(--lt-line-1)',
              borderRadius: 'var(--lt-r-sm)', padding: '3px 8px', cursor: 'pointer',
            }}>Alle</button>
          )}
        </div>
        {treeError ? (
          <div style={{ fontSize: 12, color: 'var(--lt-err)' }}>{treeError}</div>
        ) : notBuilt ? (
          <div style={{ fontSize: 12, color: 'var(--lt-fg-3)', lineHeight: 1.5 }}>
            Noch kein Artikelindex aufgebaut. Ein Administrator kann ihn im Admin-Bereich anlegen.
          </div>
        ) : tree === null ? (
          <div style={{ fontSize: 12, color: 'var(--lt-fg-3)' }}>Lädt…</div>
        ) : tree.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--lt-fg-3)' }}>Keine Wörterbücher freigegeben.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {tree.map((r) => (
              <label key={r.resource_id} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '5px 4px',
                borderRadius: 'var(--lt-r-sm)', cursor: 'pointer', fontSize: 12.5,
              }}>
                <input type="checkbox" checked={selectedResources.has(r.resource_id)} onChange={() => toggleResource(r.resource_id)} />
                <Icon name="book" size={12} style={{ color: 'var(--lt-primary)', flexShrink: 0 }} />
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.resource_id}</span>
                <span style={{ fontSize: 10, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-4)' }}>{r.article_count}</span>
              </label>
            ))}
          </div>
        )}
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--lt-fg-4)' }}>
          {selectedResources.size === 0 ? 'Keine Auswahl = alle freigegebenen Wörterbücher.' : `${selectedResources.size} ausgewählt.`}
        </div>
      </div>
    </div>
  )
}

export function ArtikelsucheConfigPane({ layout }: { layout: LayoutMode }) {
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
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Artikelsuche</h2>
        <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12, lineHeight: 1.45 }}>
          Artikel per Dateiname finden und als XML ansehen.
        </p>
      </div>
      <ArtikelsucheConfig />
    </section>
  )
}

// ============ Main pane (Treffer + XML-Vorschau) ============

function hitKey(hit: DbSearchHit): string { return `${hit.resource_id} ${hit.source_path}` }

function ResultRow({ hit, active, onClick }: { hit: DbSearchHit; active: boolean; onClick: () => void }) {
  const filename = hit.source_path.split('/').pop() ?? hit.source_path
  return (
    <button onClick={onClick} style={{
      display: 'flex', flexDirection: 'column', gap: 3, width: '100%', textAlign: 'left',
      padding: '8px 12px', background: active ? 'var(--lt-primary-soft)' : 'transparent',
      border: 'none', borderLeft: active ? '3px solid var(--lt-primary)' : '3px solid transparent',
      borderBottom: '1px solid var(--lt-line-1)', cursor: 'pointer',
    }}>
      <span style={{
        fontFamily: 'var(--lt-font-mono)', fontSize: 12.5, fontWeight: 500,
        color: active ? 'var(--lt-primary)' : 'var(--lt-fg-1)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>{filename}</span>
      <span style={{ fontSize: 11, color: 'var(--lt-fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {hit.lemma ?? hit.article_id}
        <span style={{ color: 'var(--lt-fg-4)', marginLeft: 6 }}>{hit.resource_id} / {hit.letter}</span>
      </span>
    </button>
  )
}

function XmlViewer({ content }: { content: string }) {
  const lines = content.split('\n')
  const numWidth = String(lines.length).length
  return (
    <div style={{
      flex: 1, overflow: 'auto', background: 'var(--lt-bg-1)', padding: '10px 0',
      fontFamily: 'var(--lt-font-mono)', fontSize: 12, lineHeight: 1.55,
    }}>
      {lines.map((text, i) => (
        <div key={i} style={{ display: 'flex', padding: '0 12px' }}>
          <span style={{
            color: 'var(--lt-fg-4)', userSelect: 'none', flexShrink: 0,
            width: `${numWidth}ch`, textAlign: 'right', marginRight: '1em',
          }}>{i + 1}</span>
          <span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{text || ' '}</span>
        </div>
      ))}
    </div>
  )
}

function ResultsList({ scrollable, onSelect }: { scrollable: boolean; onSelect?: () => void }) {
  const { query, results, searching, searchError, selected, select } = useArtikelsuche()
  return (
    <div style={scrollable ? { flex: 1, overflowY: 'auto' } : undefined}>
      {query.trim() === '' ? (
        <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>
          Dateiname eingeben, um Artikel zu finden.
        </div>
      ) : searchError ? (
        <div style={{ padding: '20px 16px', color: 'var(--lt-err)', fontSize: 13 }}>{searchError}</div>
      ) : searching ? (
        <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>Sucht…</div>
      ) : results.length === 0 ? (
        <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>Keine Treffer.</div>
      ) : (
        results.map((hit) => (
          <ResultRow key={hitKey(hit)} hit={hit} active={selected != null && hitKey(selected) === hitKey(hit)}
            onClick={() => { select(hit); onSelect?.() }} />
        ))
      )}
    </div>
  )
}

function ResultsHeader() {
  const { query, results, searching } = useArtikelsuche()
  return (
    <>
      <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Treffer</h3>
      {query.trim() !== '' && !searching && (
        <span style={{ fontFamily: 'var(--lt-font-mono)', fontSize: 12, color: 'var(--lt-fg-3)' }}>{results.length}</span>
      )}
    </>
  )
}

function ArticleViewer() {
  const { content, contentLoading, contentError } = useArtikelsuche()
  if (contentError) return <div style={{ padding: '20px 16px', color: 'var(--lt-err)', fontSize: 13 }}>{contentError}</div>
  if (contentLoading || content == null) {
    return <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lt-fg-3)', fontSize: 13, minHeight: 120 }}>Lädt…</div>
  }
  return <XmlViewer content={content} />
}

export function ArtikelsucheMain() {
  const isMobile = useIsMobile()
  const { selected } = useArtikelsuche()
  const [showDetail, setShowDetail] = useState(false)

  if (isMobile) {
    return (
      <main style={{ display: 'flex', flexDirection: 'column' }}>
        {showDetail && selected ? (
          <>
            <div style={{
              height: 44, flexShrink: 0, padding: '0 8px', display: 'flex', alignItems: 'center', gap: 8,
              borderBottom: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)',
            }}>
              <button onClick={() => setShowDetail(false)} style={{
                width: 32, height: 32, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                background: 'transparent', border: 'none', color: 'var(--lt-fg-2)', cursor: 'pointer',
              }}>
                <Icon name="chevron" size={14} style={{ transform: 'rotate(180deg)' }} />
              </button>
              <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {selected.source_path}
              </span>
            </div>
            <ArticleViewer />
          </>
        ) : (
          <>
            <div style={{
              height: 44, flexShrink: 0, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 8,
              borderBottom: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)',
            }}>
              <ResultsHeader />
            </div>
            <ResultsList scrollable={false} onSelect={() => setShowDetail(true)} />
          </>
        )}
      </main>
    )
  }

  return (
    <main style={{ gridArea: 'main', display: 'flex', overflow: 'hidden' }}>
      <div style={{ width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)' }}>
        <div style={{
          height: 44, flexShrink: 0, padding: '0 12px', display: 'flex', alignItems: 'center', gap: 8,
          borderBottom: '1px solid var(--lt-line-1)',
        }}>
          <ResultsHeader />
        </div>
        <ResultsList scrollable />
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{
          height: 44, flexShrink: 0, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 10,
          borderBottom: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)',
        }}>
          <Icon name="file" size={14} style={{ color: 'var(--lt-fg-3)' }} />
          <span style={{
            fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{selected ? selected.source_path : 'Kein Artikel ausgewählt'}</span>
        </div>
        {!selected ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>
            Einen Treffer links auswählen, um den Artikel als XML anzuzeigen.
          </div>
        ) : (
          <ArticleViewer />
        )}
      </div>
    </main>
  )
}
