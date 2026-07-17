import { useMemo, useState, type CSSProperties } from 'react'
import { Icon } from '../design/icons'
import { Diff, HBar, Kbd, kc, Sparkbars, type SparkDatum } from '../design/widgets'
import type { Column } from '../modules/registry'
import { useWorkbench } from '../state/workbench'

const PAGE_SIZE = 50

export function str(v: unknown): string { return v == null ? '' : String(v) }

export function aggregate(rows: Record<string, unknown>[], key: string, top = 7): SparkDatum[] {
  const counts = new Map<string, number>()
  for (const r of rows) {
    const k = str(r[key])
    if (!k) continue
    counts.set(k, (counts.get(k) ?? 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, top).map(([name, count]) => ({ name, count }))
}

export function toCsv(rows: Record<string, unknown>[], columns: Column[]): string {
  const esc = (s: string) => /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  const head = columns.map((c) => esc(c.label)).join(';')
  const body = rows.map((r) => columns.map((c) => esc(str(r[c.key]))).join(';')).join('\n')
  return head + '\n' + body
}

function StatCell({ label, value, sub, children, noBorder }: {
  label: string; value: string; sub?: string; children?: React.ReactNode; noBorder?: boolean
}) {
  return (
    <div style={{
      padding: '10px 16px', borderRight: noBorder ? 'none' : '1px solid var(--lt-line-1)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
    }}>
      <div>
        <div className="lt-eyebrow" style={{ fontSize: 10 }}>{label}</div>
        <div style={{ fontSize: 14, fontWeight: 600, marginTop: 1 }}>{value}</div>
        {sub && <div style={{ fontSize: 10.5, color: 'var(--lt-fg-3)', fontFamily: 'var(--lt-font-mono)' }}>{sub}</div>}
      </div>
      {children}
    </div>
  )
}

function Cell({ col, row }: { col: Column; row: Record<string, unknown> }) {
  const v = str(row[col.key])
  const base: CSSProperties = { padding: '6px 12px', verticalAlign: 'middle' }
  if (col.diffWith) return <td style={base}><Diff a={str(row[col.diffWith])} b={v} /></td>
  if (col.chip) return (
    <td style={base}>
      <span style={{ fontFamily: 'var(--lt-font-mono)', fontSize: 11, padding: '1px 6px', background: 'var(--lt-bg-2)', color: 'var(--lt-fg-2)', borderRadius: 3 }}>{v}</span>
    </td>
  )
  const style: CSSProperties = {
    ...base,
    textAlign: col.align === 'right' ? 'right' : 'left',
    fontFamily: col.mono ? 'var(--lt-font-mono)' : 'inherit',
    color: col.danger ? 'var(--lt-err)' : col.italic ? 'var(--lt-fg-2)' : undefined,
    fontStyle: col.italic ? 'italic' : undefined,
    whiteSpace: col.italic ? 'nowrap' : undefined,
    overflow: col.italic ? 'hidden' : undefined,
    textOverflow: col.italic ? 'ellipsis' : undefined,
    fontSize: col.mono && (col.key === 'quelle') ? 11 : undefined,
  }
  return <td style={style}>{v}</td>
}

export function ResultsPane() {
  const { module, result, running, error, directory } = useWorkbench()
  const columns = module.columns
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)

  const rows = result?.results ?? []
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) => columns.some((c) => str(r[c.key]).toLowerCase().includes(q)))
  }, [rows, query, columns])

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pages - 1)
  const pageRows = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE)

  const hasTag = columns.some((c) => c.key === 'tag')
  const byTag = hasTag ? aggregate(rows, 'tag') : []
  const byVolume = aggregate(rows, 'quelle')

  const download = () => {
    const blob = new Blob([toCsv(filtered, columns)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${module.id}_results.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <main style={{ gridArea: 'main', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{
        height: 44, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 12,
        borderBottom: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)',
      }}>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Ergebnisse</h3>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, fontFamily: 'var(--lt-font-mono)', fontSize: 12 }}>
          <span style={{ fontWeight: 600 }}>{result?.result_count ?? 0}</span>
          <span style={{ color: 'var(--lt-fg-3)' }}>Treffer</span>
          {result && <>
            <span style={{ color: 'var(--lt-fg-4)', padding: '0 6px' }}>·</span>
            <span style={{ color: 'var(--lt-fg-3)' }}>aus {result.files_checked} Dateien</span>
            <span style={{ color: 'var(--lt-fg-4)', padding: '0 6px' }}>·</span>
            <span style={{ color: 'var(--lt-fg-3)' }}>{(result.duration_ms / 1000).toFixed(2)} s</span>
          </>}
        </div>
        <span style={{ flex: 1 }} />
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', background: 'var(--lt-bg-1)',
          border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-sm)', fontSize: 12, color: 'var(--lt-fg-3)', width: 220,
        }}>
          <Icon name="filter" size={11} style={{ flexShrink: 0 }} />
          <input value={query} onChange={(e) => { setQuery(e.target.value); setPage(0) }} placeholder="Treffer filtern…"
            style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 12, color: 'var(--lt-fg-1)' }} />
          <Kbd>{kc('F')}</Kbd>
        </div>
      </div>

      {/* Stat strip */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1.6fr 1fr', borderBottom: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)' }}>
        <StatCell label="Treffer gesamt" value={String(result?.result_count ?? 0)} sub={result ? `${(result.duration_ms / 1000).toFixed(2)} s` : '–'} />
        <StatCell label={hasTag ? 'Tags' : 'Quellen'} value={hasTag ? `${byTag.length} betroffen` : `${byVolume.length}`}
          sub={(hasTag ? byTag : byVolume)[0] ? `${(hasTag ? byTag : byVolume)[0].name} · ${(hasTag ? byTag : byVolume)[0].count}` : '–'}>
          <Sparkbars data={hasTag ? byTag : byVolume} width={150} height={24} color={hasTag ? 'var(--lt-info)' : 'var(--lt-warn)'} interactive />
        </StatCell>
        <StatCell label="Dateien" value={String(result?.files_checked ?? 0)} sub="geprüft" noBorder>
          <div style={{ width: 60 }}><HBar value={1} max={1} height={6} /></div>
        </StatCell>
      </div>

      {/* Table */}
      <div className="agm-grid" style={{ flex: 1, overflow: 'auto', background: 'var(--lt-bg-0)' }}>
        {error ? (
          <div style={{ padding: '20px 16px', color: 'var(--lt-err)', fontSize: 13 }}>{error}</div>
        ) : running ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>Prüfung läuft…</div>
        ) : !result ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>
            {directory ? 'Bereit. „Prüfen" startet die Analyse.' : 'Datenverzeichnis angeben und „Prüfen".'}
          </div>
        ) : (
          <table className="agm-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, tableLayout: 'fixed', background: 'var(--lt-bg-0)' }}>
            <colgroup>{columns.map((c) => <col key={c.key} style={{ width: c.width ? c.width : 'auto' }} />)}</colgroup>
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c.key} className="agm-th" style={{
                    height: 40, padding: 0, borderBottom: '1px solid var(--lt-line-2)', background: 'var(--lt-bg-0)',
                    position: 'sticky', top: 0, zIndex: 1, textAlign: 'left',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: c.align === 'right' ? 'flex-end' : 'flex-start', gap: 6, height: '100%', padding: '0 12px' }}>
                      <span style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--lt-fg-1)' }}>{c.label}</span>
                    </div>
                    <span className="agm-resizer" />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.length === 0 ? (
                <tr><td colSpan={columns.length} style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 12.5 }}>Keine Treffer.</td></tr>
              ) : pageRows.map((r, i) => (
                <tr key={i} className="agm-row" style={{ borderBottom: '1px solid var(--lt-line-1)' }}>
                  {columns.map((c) => <Cell key={c.key} col={c} row={r} />)}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      <div style={{
        height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 16, padding: '0 16px',
        borderTop: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)', fontSize: 12, color: 'var(--lt-fg-2)',
      }}>
        <button onClick={download} disabled={!result || filtered.length === 0} style={{
          display: 'inline-flex', alignItems: 'center', gap: 7, background: 'var(--lt-primary)', color: 'var(--lt-on-primary)',
          border: '1px solid var(--lt-primary)', height: 36, padding: '0 14px', borderRadius: 'var(--lt-r-md)',
          fontSize: 13, fontWeight: 600, cursor: 'pointer', opacity: !result || filtered.length === 0 ? 0.5 : 1,
        }}><Icon name="download" size={13} /> CSV herunterladen</button>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)' }}>
          {filtered.length === 0 ? '0' : `${safePage * PAGE_SIZE + 1}–${Math.min((safePage + 1) * PAGE_SIZE, filtered.length)}`} von {filtered.length}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <PageBtn dir="prev" disabled={safePage <= 0} onClick={() => setPage(safePage - 1)} />
          <span style={{ padding: '0 8px', fontFamily: 'var(--lt-font-mono)' }}>Seite <b>{safePage + 1}</b> von {pages}</span>
          <PageBtn dir="next" disabled={safePage >= pages - 1} onClick={() => setPage(safePage + 1)} />
        </div>
      </div>
    </main>
  )
}

function PageBtn({ dir, disabled, onClick }: { dir: 'prev' | 'next'; disabled: boolean; onClick: () => void }) {
  return (
    <button disabled={disabled} onClick={onClick} style={{
      width: 26, height: 26, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: 'transparent', border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-xs)',
      color: disabled ? 'var(--lt-fg-4)' : 'var(--lt-fg-2)', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.5 : 1,
    }}>
      <span style={{ display: 'inline-flex', transform: dir === 'prev' ? 'rotate(180deg)' : 'none' }}><Icon name="chevron" size={10} /></span>
    </button>
  )
}
