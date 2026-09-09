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

type Mode = 'Upload' | 'Datenbank'

export function DataDialog() {
  const { setDataDialogOpen, applyDataset } = useWorkbench()
  const [mode, setMode] = useState<Mode>('Datenbank')
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

  // ── Upload ──
  const fileRef = useRef<HTMLInputElement>(null)
  const folderRef = useRef<HTMLInputElement>(null)
  const [uploadTarget, setUploadTarget] = useState<'file' | 'folder' | null>(null)
  // Callback-Ref statt useEffect: der Ordner-Input steckt im mode==='Upload'-Zweig
  // und existiert bei Dialog-Mount (mode ist anfangs 'Datenbank') noch nicht —
  // ein useEffect mit [] verpasst ihn dann dauerhaft. Der Callback feuert
  // zuverlässig bei jedem tatsächlichen Mount des Elements.
  const setFolderRef = (el: HTMLInputElement | null) => {
    folderRef.current = el
    if (!el) return
    // webkitdirectory/directory sind nicht standardisiert und fehlen daher in
    // den JSX-Typings — als DOM-Attribute statt als Props setzen.
    for (const attr of ['webkitdirectory', 'directory']) el.setAttribute(attr, '')
  }
  const doUpload = async (files: FileList | null, target: 'file' | 'folder') => {
    if (!files || files.length === 0) return
    setBusy(true); setUploadTarget(target); setError(''); setInfo('')
    try {
      const ds = await dataApi.upload(Array.from(files))
      const errs = ds.errors && ds.errors.length ? ` (${ds.errors.length} übersprungen)` : ''
      finish(ds.directory, ds.file_count, `${ds.file_count} XML-Dateien geladen${errs}. „Weiter", um zu prüfen.`)
    } catch (e) { setError(String(e)) } finally { setBusy(false); setUploadTarget(null) }
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
          <Segmented options={['Upload', 'Datenbank']} value={mode} onChange={(v) => { setMode(v as Mode); setError(''); setInfo('') }} />

          {mode === 'Upload' && (
            <div style={card}>
              <div style={{ fontSize: 12, color: 'var(--lt-fg-3)', marginBottom: 10 }}>
                XML- oder ZIP-Dateien hochladen (ZIP wird entpackt), oder einen ganzen Ordner (Unterordner bleiben erhalten).
              </div>
              <input ref={fileRef} type="file" multiple accept=".xml,.zip" style={{ display: 'none' }} onChange={(e) => doUpload(e.target.files, 'file')} />
              <input ref={setFolderRef} type="file" multiple style={{ display: 'none' }} onChange={(e) => doUpload(e.target.files, 'folder')} />
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => fileRef.current?.click()} disabled={busy} style={{ ...btnPrimary, flex: 1 }}>
                  <Icon name="upload" size={13} /> {uploadTarget === 'file' ? 'Lädt…' : 'Dateien auswählen'}
                </button>
                <button onClick={() => folderRef.current?.click()} disabled={busy} style={{ ...btnPrimary, flex: 1 }}>
                  <Icon name="folder" size={13} /> {uploadTarget === 'folder' ? 'Lädt…' : 'Ordner auswählen'}
                </button>
              </div>
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
