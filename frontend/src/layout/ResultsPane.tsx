import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import type { CellStyle, ColDef, ICellRendererParams, SelectionChangedEvent } from 'ag-grid-community'
import { ltGridTheme } from '../design/agGrid'
import { Icon } from '../design/icons'
import { Diff, HBar, Kbd, kc, Sparkbars, type SparkDatum } from '../design/widgets'
import type { Column } from '../modules/registry'
import { useWorkbench } from '../state/workbench'
import { FilePreviewDialog, type FilePreviewTarget } from './FilePreviewDialog'

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

function ChipCellRenderer({ value }: ICellRendererParams) {
  return (
    <span style={{ fontFamily: 'var(--lt-font-mono)', fontSize: 11, padding: '1px 6px', background: 'var(--lt-bg-2)', color: 'var(--lt-fg-2)', borderRadius: 3 }}>
      {str(value)}
    </span>
  )
}

interface DiffRendererParams extends ICellRendererParams { diffWith: string }
function DiffCellRenderer(p: DiffRendererParams) {
  return <Diff a={str(p.data?.[p.diffWith])} b={str(p.value)} />
}

function buildColumnDefs(columns: Column[]): ColDef[] {
  return columns.map((c): ColDef => {
    const numeric = c.align === 'right'
    const cellStyle: CellStyle = {
      ...(c.mono ? { fontFamily: 'var(--lt-font-mono)' } : {}),
      ...(c.danger ? { color: 'var(--lt-err)' } : c.italic ? { color: 'var(--lt-fg-2)' } : {}),
      ...(c.italic ? { fontStyle: 'italic' } : {}),
      ...(c.mono && c.key === 'quelle' ? { fontSize: 11 } : {}),
    }
    const col: ColDef = {
      field: c.key,
      headerName: c.label,
      width: c.width,
      flex: c.width ? undefined : 1,
      minWidth: 70,
      type: numeric ? 'rightAligned' : undefined,
      sortable: true,
      resizable: true,
      floatingFilter: true,
      filter: numeric ? 'agNumberColumnFilter' : 'agTextColumnFilter',
      cellStyle,
      valueFormatter: (p) => str(p.value),
    }
    if (c.chip) { col.cellRenderer = ChipCellRenderer; col.filter = 'agTextColumnFilter' }
    if (c.diffWith) {
      col.cellRenderer = DiffCellRenderer
      col.cellRendererParams = { diffWith: c.diffWith }
      col.filter = 'agTextColumnFilter'
    }
    return col
  })
}

export const PHASE_LABELS: Record<string, string> = {
  scanning: 'Verweise werden gezählt',
  checking: 'Ziele werden geprüft',
}

export function ResultsPane() {
  const { module, result, running, error, directory, progress } = useWorkbench()
  const columns = module.columns
  const [query, setQuery] = useState('')
  const [displayedCount, setDisplayedCount] = useState(0)
  const [selectedRow, setSelectedRow] = useState<Record<string, unknown> | null>(null)
  const [preview, setPreview] = useState<FilePreviewTarget | null>(null)
  const gridRef = useRef<AgGridReact>(null)

  const supportsPreview = columns.some((c) => c.key === 'line')

  const rows = result?.results ?? []
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) => columns.some((c) => str(r[c.key]).toLowerCase().includes(q)))
  }, [rows, query, columns])

  const colDefs = useMemo(() => buildColumnDefs(columns), [columns])
  const defaultColDef = useMemo<ColDef>(() => ({ sortable: true, resizable: true, floatingFilter: true }), [])
  const onGridStateChange = useCallback(() => {
    setDisplayedCount(gridRef.current?.api?.getDisplayedRowCount() ?? 0)
  }, [])
  const onSelectionChanged = useCallback((e: SelectionChangedEvent) => {
    setSelectedRow(e.api.getSelectedRows()[0] ?? null)
  }, [])

  useEffect(() => { setSelectedRow(null) }, [result])

  const hasTag = columns.some((c) => c.key === 'tag')
  const byTag = hasTag ? aggregate(rows, 'tag') : []
  const byVolume = aggregate(rows, 'quelle')

  const download = () => {
    gridRef.current?.api.exportDataAsCsv({ columnSeparator: ';', fileName: `${module.id}_results.csv` })
  }

  const openFile = () => {
    if (!selectedRow || !directory) return
    setPreview({
      directory,
      subdir: str(selectedRow.subdir),
      filename: str(selectedRow.filename),
      line: Number(selectedRow.line) || 0,
    })
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
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Treffer filtern…"
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
      <div style={{ flex: 1, minHeight: 0, background: 'var(--lt-bg-0)' }}>
        {error ? (
          <div style={{ padding: '20px 16px', color: 'var(--lt-err)', fontSize: 13 }}>{error}</div>
        ) : running ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>
            {progress ? (
              <div style={{ maxWidth: 320, margin: '0 auto' }}>
                <div style={{ marginBottom: 8 }}>
                  {PHASE_LABELS[progress.phase] ?? progress.phase}… ({progress.done} von {progress.total || '?'})
                </div>
                <HBar value={progress.done} max={Math.max(progress.total, 1)} height={6} />
              </div>
            ) : 'Prüfung läuft…'}
          </div>
        ) : !result ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>
            {directory ? 'Bereit. „Prüfen" startet die Analyse.' : 'Datenverzeichnis angeben und „Prüfen".'}
          </div>
        ) : (
          <AgGridReact
            ref={gridRef}
            theme={ltGridTheme}
            rowData={filtered}
            columnDefs={colDefs}
            defaultColDef={defaultColDef}
            animateRows
            suppressCellFocus
            overlayNoRowsTemplate="Keine Treffer."
            onGridReady={onGridStateChange}
            onModelUpdated={onGridStateChange}
            rowSelection={supportsPreview ? { mode: 'singleRow', checkboxes: false, enableClickSelection: true } : undefined}
            onSelectionChanged={supportsPreview ? onSelectionChanged : undefined}
          />
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
        {supportsPreview && <>
          <button onClick={openFile} disabled={!selectedRow} style={{
            display: 'inline-flex', alignItems: 'center', gap: 7, background: 'var(--lt-bg-0)', color: 'var(--lt-fg-2)',
            border: '1px solid var(--lt-line-2)', height: 36, padding: '0 14px', borderRadius: 'var(--lt-r-md)',
            fontSize: 13, fontWeight: 600, cursor: selectedRow ? 'pointer' : 'not-allowed',
            opacity: selectedRow ? 1 : 0.5,
          }}><Icon name="file" size={13} /> Datei öffnen</button>
          <span style={{ fontSize: 12, fontStyle: 'italic', color: 'var(--lt-fg-3)' }}>
            Zeile auswählen, dann 'Datei öffnen' klicken.
          </span>
        </>}
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)' }}>
          {displayedCount} von {filtered.length}
        </span>
      </div>

      {preview && <FilePreviewDialog target={preview} onClose={() => setPreview(null)} />}
    </main>
  )
}
