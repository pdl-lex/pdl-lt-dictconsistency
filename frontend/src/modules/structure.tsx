// Strukturanalyse: zusammengeführter Tag-/Attribut-/Text-Baum aller XML-
// Dateien eines Verzeichnisses. Anders als die tabellarischen Prüfungen
// (registry.ts) ist das Ergebnis ein Baum, kein flaches Zeilen-Array — die
// Seite hängt sich daher wie „API" (apiInfo.tsx) und „Admin" (AdminView.tsx)
// als Sonderseite neben ConfigPane/ResultsPane ein (siehe App.tsx: isStructure).
// Backend: POST /api/checks/structure (pdl_lt_dictconsistency/core/xml_structure.py).
import {
  createContext, useCallback, useContext, useMemo, useState,
  type CSSProperties, type ReactNode,
} from 'react'
import { Icon } from '../design/icons'
import { api, dataApi } from '../api/client'
import { DataCard } from '../layout/ConfigPane'
import { useWorkbench, type LayoutMode } from '../state/workbench'

// ============ Types ============

export interface StructureRow {
  id: string
  depth: number
  kind: 'tag' | 'attr' | 'text_content'
  label: string
  has_children: boolean
  attr_values?: string[]
  text_examples?: string[]
}

interface StructureResponse {
  results: StructureRow[]
  files_checked: number
  result_count: number
  duration_ms: number
}

interface FileEntry { subdir: string; filename: string }

function fileKey(f: FileEntry): string { return f.subdir === '.' ? f.filename : `${f.subdir}/${f.filename}` }

// ============ Pure tree helpers (ported from core/xml_structure.py's
// former Reflex counterpart — collapse/search stay client-side since they
// don't need file access) ============

function recomputeVisibility(rows: StructureRow[], collapsed: Set<string>): Map<string, boolean> {
  const visible = new Map<string, boolean>()
  const stack: { depth: number; collapsed: boolean }[] = []
  for (const row of rows) {
    while (stack.length && stack[stack.length - 1].depth >= row.depth) stack.pop()
    visible.set(row.id, stack.every((s) => !s.collapsed))
    if (row.kind === 'tag') stack.push({ depth: row.depth, collapsed: collapsed.has(row.id) })
  }
  return visible
}

interface DisplayRow { row: StructureRow; isMatch: boolean; isCollapsed: boolean }

function computeDisplayRows(rows: StructureRow[], collapsed: Set<string>, query: string): DisplayRow[] {
  const isCollapsed = (r: StructureRow) => r.kind === 'tag' && collapsed.has(r.id)
  const q = query.trim().toLowerCase()

  if (!q) {
    const visibility = recomputeVisibility(rows, collapsed)
    return rows.filter((r) => visibility.get(r.id)).map((row) => ({ row, isMatch: false, isCollapsed: isCollapsed(row) }))
  }

  const directMatch = new Set<string>()
  const matching = new Set<string>()
  for (const row of rows) {
    const hit = row.label.toLowerCase().includes(q)
      || (row.attr_values ?? []).some((v) => v.toLowerCase().includes(q))
      || (row.text_examples ?? []).some((v) => v.toLowerCase().includes(q))
    if (hit) {
      directMatch.add(row.id)
      matching.add(row.id)
      const parts = row.id.split('/')
      for (let i = 1; i < parts.length; i++) matching.add(parts.slice(0, i).join('/'))
    }
  }
  const matchedTagIds = new Set(rows.filter((r) => r.kind === 'tag' && matching.has(r.id)).map((r) => r.id))
  for (const row of rows) {
    let parentId = ''
    if (row.kind === 'attr') {
      const idx = row.id.lastIndexOf('/@')
      parentId = idx === -1 ? '' : row.id.slice(0, idx)
    } else if (row.kind === 'text_content') {
      parentId = row.id.slice(0, -'/#text'.length)
    } else continue
    if (matchedTagIds.has(parentId)) matching.add(row.id)
  }
  return rows.filter((r) => matching.has(r.id)).map((row) => ({ row, isMatch: directMatch.has(row.id), isCollapsed: isCollapsed(row) }))
}

// ============ Context ============

interface StructureState {
  rows: StructureRow[] | null
  loading: boolean
  error: string
  files: FileEntry[]
  fileFilter: string
  filesChecked: number
  durationMs: number
  analyze: () => Promise<void>
  setFileFilter: (key: string) => void
  collapsed: Set<string>
  toggle: (id: string) => void
  collapseAll: () => void
  expandAll: () => void
  query: string
  setQuery: (q: string) => void
}

const Ctx = createContext<StructureState | null>(null)

export function StructureProvider({ children }: { children: ReactNode }) {
  const { directory } = useWorkbench()
  const [allRows, setAllRows] = useState<StructureRow[] | null>(null)
  const [filteredCache, setFilteredCache] = useState<Record<string, StructureRow[]>>({})
  const [fileFilter, setFileFilterState] = useState('')
  const [files, setFiles] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [filesChecked, setFilesChecked] = useState(0)
  const [durationMs, setDurationMs] = useState(0)

  const rows = fileFilter === '' ? allRows : (filteredCache[fileFilter] ?? null)

  const analyze = useCallback(async () => {
    if (!directory.trim()) { setError('Bitte zuerst ein Datenverzeichnis angeben.'); return }
    setLoading(true); setError(''); setFileFilterState(''); setFilteredCache({})
    try {
      const [structureRes, scanRes] = await Promise.all([
        api.post<StructureResponse>('/checks/structure', { directory }),
        dataApi.scan(directory),
      ])
      setAllRows(structureRes.results)
      setFilesChecked(structureRes.files_checked)
      setDurationMs(structureRes.duration_ms)
      setFiles(scanRes.files.map((f) => ({ subdir: f.subdir, filename: f.filename })))
      setCollapsed(new Set(
        structureRes.results.filter((r) => r.kind === 'tag' && r.has_children && r.depth >= 1).map((r) => r.id),
      ))
    } catch (e) {
      setError(String(e)); setAllRows(null)
    } finally {
      setLoading(false)
    }
  }, [directory])

  const setFileFilter = useCallback((key: string) => {
    setFileFilterState(key)
    if (key === '' || filteredCache[key]) return
    const entry = files.find((f) => fileKey(f) === key)
    if (!entry) return
    setLoading(true); setError('')
    api.post<StructureResponse>('/checks/structure', { directory, files: [entry] })
      .then((res) => setFilteredCache((prev) => ({ ...prev, [key]: res.results })))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [directory, files, filteredCache])

  const toggle = useCallback((id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  const collapseAll = useCallback(() => {
    setCollapsed(new Set((rows ?? []).filter((r) => r.kind === 'tag' && r.has_children).map((r) => r.id)))
  }, [rows])

  const expandAll = useCallback(() => setCollapsed(new Set()), [])

  const value = useMemo<StructureState>(() => ({
    rows, loading, error, files, fileFilter, filesChecked, durationMs,
    analyze, setFileFilter, collapsed, toggle, collapseAll, expandAll, query, setQuery,
  }), [rows, loading, error, files, fileFilter, filesChecked, durationMs, analyze, setFileFilter, collapsed, toggle, collapseAll, expandAll, query])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStructure(): StructureState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useStructure must be used within StructureProvider')
  return v
}

// ============ Config pane ============

const card: CSSProperties = {
  background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-1)', padding: 14,
}
const btnPrimary: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  background: 'var(--lt-primary)', color: 'var(--lt-on-primary)', border: '1px solid var(--lt-primary)',
  height: 36, padding: '0 16px', borderRadius: 'var(--lt-r-md)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
}

export function StructureConfig() {
  const { rows, loading, error, analyze } = useStructure()
  return (
    <div className="cfg-scroll" style={{ overflowY: 'auto', flex: 1, background: 'var(--lt-bg-2)', padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <DataCard />
      <div style={card}>
        <div style={{ fontSize: 12, color: 'var(--lt-fg-3)', lineHeight: 1.5 }}>
          Liest alle ausgewählten Dateien und führt Tags, Attribute und Textinhalte zu einem
          gemeinsamen Baum zusammen. Attributwerte werden direkt angezeigt; Textbeispiele lassen
          sich einzeln aufdecken.
        </div>
      </div>
      {error && <div style={{ fontSize: 12, color: 'var(--lt-err)' }}>{error}</div>}
      <button onClick={() => void analyze()} disabled={loading} style={{ ...btnPrimary, opacity: loading ? 0.7 : 1 }}>
        <Icon name="play" size={12} />
        {loading ? 'Analysiere…' : rows ? 'Neu analysieren' : 'Strukturanalyse starten'}
      </button>
    </div>
  )
}

export function StructureConfigPane({ layout }: { layout: LayoutMode }) {
  return (
    <section style={{
      gridArea: 'cfg', background: 'var(--lt-bg-0)',
      borderRight: layout === 'left' ? '1px solid var(--lt-line-1)' : 'none',
      borderLeft: layout === 'right' ? '1px solid var(--lt-line-1)' : 'none',
      borderBottom: layout === 'bottom' ? '1px solid var(--lt-line-1)' : 'none',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ padding: '14px 18px 12px', background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
        <div className="lt-eyebrow" style={{ marginBottom: 4 }}>XML</div>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Strukturanalyse</h2>
        <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12, lineHeight: 1.45 }}>
          Zusammengeführter Tag-/Attribut-/Text-Baum aller Dateien.
        </p>
      </div>
      <StructureConfig />
    </section>
  )
}

// ============ Main pane (tree) ============

const iconGhost: CSSProperties = {
  width: 20, height: 20, flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  background: 'transparent', border: 'none', color: 'var(--lt-fg-3)', cursor: 'pointer', borderRadius: 3,
}
const chipBtn: CSSProperties = {
  fontSize: 10.5, padding: '1px 7px', background: 'var(--lt-bg-2)', border: '1px solid var(--lt-line-1)',
  borderRadius: 3, color: 'var(--lt-fg-3)', cursor: 'pointer',
}

function AttrValues({ row, onShowAll }: { row: StructureRow; onShowAll: (label: string, values: string[]) => void }) {
  const values = row.attr_values ?? []
  const inline = values.slice(0, 5)
  const extra = Math.max(0, values.length - 5)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexWrap: 'wrap', minWidth: 0 }}>
      <span style={{ color: 'var(--lt-fg-4)', fontFamily: 'var(--lt-font-mono)', fontSize: 11 }}>=</span>
      {inline.map((v, i) => (
        <span key={i} style={{
          fontFamily: 'var(--lt-font-mono)', fontSize: 11, padding: '1px 6px', borderRadius: 3,
          background: 'var(--lt-info-soft)', color: 'var(--lt-info)',
        }}>{v}</span>
      ))}
      {extra > 0 && <button style={chipBtn} onClick={() => onShowAll(row.label, values)}>+{extra} weitere</button>}
      {values.length === 0 && <span style={{ color: 'var(--lt-fg-4)', fontFamily: 'var(--lt-font-mono)', fontSize: 11 }}>…</span>}
    </span>
  )
}

function TextExample({ row, shownIndex, onReveal, onShowAll }: {
  row: StructureRow; shownIndex: number | undefined; onReveal: (row: StructureRow) => void
  onShowAll: (label: string, values: string[]) => void
}) {
  const examples = row.text_examples ?? []
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
      <span style={{ color: 'var(--lt-fg-4)', fontFamily: 'var(--lt-font-mono)', fontSize: 11 }}>=</span>
      {examples.length === 0 ? (
        <span style={{ color: 'var(--lt-fg-4)', fontFamily: 'var(--lt-font-mono)', fontSize: 11 }}>…</span>
      ) : shownIndex == null ? (
        <button style={chipBtn} onClick={() => onReveal(row)}>Beispiel</button>
      ) : (
        <>
          <span style={{
            fontFamily: 'var(--lt-font-mono)', fontSize: 12, color: 'var(--lt-fg-1)',
            maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{examples[shownIndex % examples.length]}</span>
          {examples.length > 1 && (
            <button style={iconGhost} title="Anderes Beispiel" onClick={() => onReveal(row)}>
              <Icon name="refresh" size={10} />
            </button>
          )}
        </>
      )}
      {examples.length > 1 && (
        <button style={chipBtn} onClick={() => onShowAll(row.label, examples)}>alle ({examples.length})</button>
      )}
    </span>
  )
}

function TreeRow({ row, isMatch, isCollapsed, shownIndex, onToggle, onReveal, onShowAll }: {
  row: StructureRow; isMatch: boolean; isCollapsed: boolean; shownIndex: number | undefined
  onToggle: (id: string) => void; onReveal: (row: StructureRow) => void
  onShowAll: (label: string, values: string[]) => void
}) {
  const isTag = row.kind === 'tag'
  const color = isTag ? 'var(--lt-primary)' : row.kind === 'attr' ? 'var(--lt-info)' : 'var(--lt-fg-3)'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6, minWidth: 'max-content',
      paddingLeft: row.depth * 20, paddingTop: 2, paddingBottom: 2, paddingRight: 8,
      background: isMatch ? 'var(--lt-warn-soft)' : 'transparent',
      borderLeft: isMatch ? '2px solid var(--lt-warn)' : '2px solid transparent',
      borderRadius: 3,
    }}>
      {isTag && row.has_children ? (
        <button style={iconGhost} onClick={() => onToggle(row.id)}>
          <Icon name={isCollapsed ? 'chevron' : 'chevDown'} size={11} />
        </button>
      ) : <span style={{ width: 20, flexShrink: 0 }} />}
      <span style={{
        fontFamily: 'var(--lt-font-mono)', fontSize: 12.5, color, whiteSpace: 'nowrap',
        fontWeight: isTag ? 600 : 400,
      }}>{row.label}</span>
      {row.kind === 'attr' && <AttrValues row={row} onShowAll={onShowAll} />}
      {row.kind === 'text_content' && <TextExample row={row} shownIndex={shownIndex} onReveal={onReveal} onShowAll={onShowAll} />}
    </div>
  )
}

function ValuesModal({ label, values, onClose }: { label: string; values: string[]; onClose: () => void }) {
  return (
    <div onClick={onClose} style={{
      position: 'absolute', inset: 0, zIndex: 200, background: 'rgba(8,12,10,0.42)', backdropFilter: 'blur(1.5px)',
      display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: '10%',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 480, maxWidth: '90%', maxHeight: '70vh', background: 'var(--lt-bg-2)', border: '1px solid var(--lt-line-2)',
        borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-pop)', overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', background: 'var(--lt-bg-0)', borderBottom: '1px solid var(--lt-line-1)' }}>
          <span style={{ fontFamily: 'var(--lt-font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--lt-info)', flex: 1 }}>{label}</span>
          <Icon name="x" size={14} style={{ cursor: 'pointer', color: 'var(--lt-fg-3)' }} onClick={onClose} />
        </div>
        <div style={{ padding: 14, overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: 5 }}>
          {values.map((v, i) => (
            <span key={i} style={{
              fontFamily: 'var(--lt-font-mono)', fontSize: 12, padding: '3px 8px', borderRadius: 4,
              background: 'var(--lt-info-soft)', color: 'var(--lt-info)',
            }}>{v}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

export function StructureMain() {
  const {
    rows, loading, error, files, fileFilter, filesChecked, durationMs,
    setFileFilter, collapsed, toggle, collapseAll, expandAll, query, setQuery,
  } = useStructure()
  const [modal, setModal] = useState<{ label: string; values: string[] } | null>(null)
  const [shown, setShown] = useState<Record<string, number>>({})

  const display = useMemo(() => rows ? computeDisplayRows(rows, collapsed, query) : [], [rows, collapsed, query])
  const sortedFiles = useMemo(() => [...files].sort((a, b) => fileKey(a).localeCompare(fileKey(b))), [files])

  const reveal = (row: StructureRow) => {
    const n = row.text_examples?.length ?? 0
    if (n === 0) return
    setShown((prev) => ({ ...prev, [row.id]: ((prev[row.id] ?? -1) + 1) % n }))
  }

  return (
    <main style={{ gridArea: 'main', display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
      {/* Toolbar */}
      <div style={{
        height: 44, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 12,
        borderBottom: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)',
      }}>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Struktur</h3>
        {rows && (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, fontFamily: 'var(--lt-font-mono)', fontSize: 12 }}>
            <span style={{ fontWeight: 600 }}>{rows.length}</span>
            <span style={{ color: 'var(--lt-fg-3)' }}>Knoten</span>
            <span style={{ color: 'var(--lt-fg-4)', padding: '0 6px' }}>·</span>
            <span style={{ color: 'var(--lt-fg-3)' }}>aus {filesChecked} Dateien</span>
            <span style={{ color: 'var(--lt-fg-4)', padding: '0 6px' }}>·</span>
            <span style={{ color: 'var(--lt-fg-3)' }}>{(durationMs / 1000).toFixed(2)} s</span>
          </div>
        )}
        <span style={{ flex: 1 }} />
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', background: 'var(--lt-bg-1)',
          border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-sm)', fontSize: 12, color: 'var(--lt-fg-3)', width: 220,
        }}>
          <Icon name="search" size={11} style={{ flexShrink: 0 }} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tags, Attribute, Inhalte…"
            style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 12, color: 'var(--lt-fg-1)' }} />
        </div>
      </div>

      {/* Sub-toolbar: file filter + expand/collapse */}
      {rows && (
        <div style={{
          height: 40, flexShrink: 0, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 8,
          borderBottom: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)',
        }}>
          <Icon name="filter" size={11} style={{ color: 'var(--lt-fg-4)' }} />
          <select value={fileFilter} onChange={(e) => setFileFilter(e.target.value)} style={{
            fontSize: 12, fontFamily: 'var(--lt-font-mono)', padding: '4px 6px', background: 'var(--lt-bg-1)',
            border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', maxWidth: 320,
          }}>
            <option value="">Alle Dateien ({files.length})</option>
            {sortedFiles.map((f) => <option key={fileKey(f)} value={fileKey(f)}>{fileKey(f)}</option>)}
          </select>
          <span style={{ flex: 1 }} />
          <button style={chipBtn} onClick={collapseAll}>Alles einklappen</button>
          <button style={chipBtn} onClick={expandAll}>Alles ausklappen</button>
        </div>
      )}

      {/* Tree */}
      <div style={{ flex: 1, overflow: 'auto', background: 'var(--lt-bg-0)', padding: '8px 4px' }}>
        {error ? (
          <div style={{ padding: '20px 16px', color: 'var(--lt-err)', fontSize: 13 }}>{error}</div>
        ) : loading && !rows ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>Analysiere…</div>
        ) : !rows ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>
            „Strukturanalyse starten" liest alle Dateien und baut den Baum auf.
          </div>
        ) : loading ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>Lade Datei…</div>
        ) : display.length === 0 ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>Keine passenden Einträge gefunden.</div>
        ) : (
          display.map(({ row, isMatch, isCollapsed }) => (
            <TreeRow key={row.id} row={row} isMatch={isMatch} isCollapsed={isCollapsed}
              shownIndex={shown[row.id]} onToggle={toggle} onReveal={reveal}
              onShowAll={(label, values) => setModal({ label, values })} />
          ))
        )}
      </div>

      {modal && <ValuesModal label={modal.label} values={modal.values} onClose={() => setModal(null)} />}
    </main>
  )
}
