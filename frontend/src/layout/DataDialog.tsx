import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Icon } from '../design/icons'
import { HBar, Segmented } from '../design/widgets'
import { dataApi, type DbSelection } from '../api/client'
import { useWorkbench } from '../state/workbench'
import { DbTree } from './DbTree'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const POLL_INTERVAL_MS = 500

const card: CSSProperties = {
  background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-1)', padding: 14,
}
const inputStyle: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '7px 9px', fontSize: 12,
  background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', outline: 'none', fontFamily: 'var(--lt-font-mono)',
}
const btnPrimary: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
  background: 'var(--lt-primary)', color: 'var(--lt-on-primary)', border: '1px solid var(--lt-primary)',
  height: 34, padding: '0 14px', borderRadius: 'var(--lt-r-md)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
}
const btnLoaded: CSSProperties = {
  ...btnPrimary,
  background: 'var(--lt-fg-4)', border: '1px solid var(--lt-fg-4)', cursor: 'default',
}
const selectionSignature = (s: DbSelection) =>
  JSON.stringify([[...s.resource_ids].sort(), [...s.resource_letters].sort(), [...s.articles].sort()])

type Mode = 'Verzeichnis-Pfad' | 'Upload' | 'Datenbank'

export function DataDialog() {
  const { setDataDialogOpen, applyDataset, directory } = useWorkbench()
  const [mode, setMode] = useState<Mode>('Verzeichnis-Pfad')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  // Reset true on every effect run (incl. StrictMode's dev-only simulated
  // remount), not just initialized once — otherwise the mount->cleanup->
  // remount cycle permanently poisons a useRef(true)-style flag on first render.
  const mountedRef = useRef(true)

  const close = () => setDataDialogOpen(false)
  useEffect(() => {
    mountedRef.current = true
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); mountedRef.current = false }
  }, [])

  const finish = (dir: string, count: number, note?: string) => {
    applyDataset(dir, count)
    if (note) { setInfo(note); setError('') } else close()
  }

  // ── Verzeichnis-Pfad ──
  const [path, setPath] = useState(directory)
  const pathLoaded = path.trim() !== '' && path.trim() === directory
  const scanPath = async () => {
    if (pathLoaded) return
    setBusy(true); setError(''); setInfo('')
    try {
      const ds = await dataApi.scan(path)
      finish(ds.directory, ds.file_count)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  // ── Upload ──
  const fileRef = useRef<HTMLInputElement>(null)
  const doUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setBusy(true); setError(''); setInfo('')
    try {
      const ds = await dataApi.upload(Array.from(files))
      const errs = ds.errors && ds.errors.length ? ` (${ds.errors.length} übersprungen)` : ''
      finish(ds.directory, ds.file_count, `${ds.file_count} XML-Dateien geladen${errs}. „Weiter", um zu prüfen.`)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  // ── Datenbank (wbdb) ──
  const [selection, setSelection] = useState<DbSelection>({ resource_ids: [], resource_letters: [], articles: [] })
  const [selectedCount, setSelectedCount] = useState(0)
  const [loadedSignature, setLoadedSignature] = useState<string | null>(null)
  const [loadProgress, setLoadProgress] = useState<{ done: number; total: number } | null>(null)
  const dbLoaded = selectedCount > 0 && loadedSignature === selectionSignature(selection)
  const loadDbSelection = async () => {
    if (selectedCount === 0 || dbLoaded) return
    setBusy(true); setError(''); setInfo('')
    try {
      const { job_id, total } = await dataApi.dbLoadSelection(selection)
      setLoadProgress({ done: 0, total })
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await sleep(POLL_INTERVAL_MS)
        if (!mountedRef.current) return
        const s = await dataApi.dbLoadStatus(job_id)
        setLoadProgress({ done: s.done, total: s.total })
        if (s.status === 'error') throw new Error(s.error ?? 'Fehler beim Laden.')
        if (s.status === 'ok' && s.result) {
          setLoadedSignature(selectionSignature(selection))
          finish(s.result.directory, s.result.file_count, `${s.result.file_count} Artikel aus der Datenbank geladen. „Weiter", um zu prüfen.`)
          return
        }
      }
    } catch (e) { setError(String(e)) } finally { setBusy(false); setLoadProgress(null) }
  }

  return (
    <div onClick={close} style={{
      position: 'absolute', inset: 0, zIndex: 200, background: 'rgba(8,12,10,0.42)', backdropFilter: 'blur(1.5px)',
      display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: '8%',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 'min(720px, 92vw)', background: 'var(--lt-bg-2)', border: '1px solid var(--lt-line-2)',
        borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-pop)', overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', background: 'var(--lt-bg-0)', borderBottom: '1px solid var(--lt-line-1)' }}>
          <Icon name="folder" size={15} style={{ color: 'var(--lt-primary)' }} />
          <span style={{ fontSize: 14, fontWeight: 600, flex: 1 }}>Daten wählen</span>
          <Icon name="x" size={14} style={{ cursor: 'pointer', color: 'var(--lt-fg-3)' }} onClick={close} />
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Segmented options={['Verzeichnis-Pfad', 'Upload', 'Datenbank']} value={mode} onChange={(v) => { setMode(v as Mode); setError(''); setInfo('') }} />

          {mode === 'Verzeichnis-Pfad' && (
            <div style={card}>
              <div style={{ fontSize: 12, color: 'var(--lt-fg-3)', marginBottom: 8 }}>Pfad zu einem XML-Verzeichnis auf dem Server.</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input value={path} onChange={(e) => setPath(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && scanPath()} placeholder="/pfad/zu/xml" style={inputStyle} />
                <button onClick={scanPath} disabled={busy || !path.trim() || pathLoaded} style={pathLoaded ? btnLoaded : btnPrimary}>{busy ? '…' : 'Laden'}</button>
              </div>
            </div>
          )}

          {mode === 'Upload' && (
            <div style={card}>
              <div style={{ fontSize: 12, color: 'var(--lt-fg-3)', marginBottom: 10 }}>XML- oder ZIP-Dateien hochladen (ZIP wird entpackt).</div>
              <input ref={fileRef} type="file" multiple accept=".xml,.zip" style={{ display: 'none' }} onChange={(e) => doUpload(e.target.files)} />
              <button onClick={() => fileRef.current?.click()} disabled={busy} style={{ ...btnPrimary, width: '100%' }}>
                <Icon name="upload" size={13} /> {busy ? 'Lädt…' : 'Dateien auswählen'}
              </button>
            </div>
          )}

          {mode === 'Datenbank' && (
            <div style={{ ...card, padding: 8 }}>
              <DbTree onSelectionChange={(sel, count) => { setSelection(sel); setSelectedCount(count) }} />
              <div style={{ padding: '8px 2px 2px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <button onClick={loadDbSelection} disabled={busy || selectedCount === 0 || dbLoaded} style={{ ...(dbLoaded ? btnLoaded : btnPrimary), width: '100%' }}>
                  {loadProgress ? `Lädt … ${loadProgress.done} / ${loadProgress.total}` : `Laden${selectedCount ? ` (${selectedCount})` : ''}`}
                </button>
                {loadProgress && <HBar value={loadProgress.done} max={loadProgress.total} height={5} />}
              </div>
            </div>
          )}

          {error && <div style={{ fontSize: 12, color: 'var(--lt-err)' }}>{error}</div>}
          {info && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ flex: 1, fontSize: 12, color: 'var(--lt-primary)' }}>{info}</span>
              <button onClick={close} style={btnPrimary}>Weiter</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
