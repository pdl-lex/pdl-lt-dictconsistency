import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Icon } from '../design/icons'
import { Segmented } from '../design/widgets'
import { dataApi, type Datasource, type WbdbResource } from '../api/client'
import { useWorkbench } from '../state/workbench'

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

type Mode = 'Server-Pfad' | 'Upload' | 'Vorliegende Daten' | 'Datenbank'

export function DataDialog() {
  const { setDataDialogOpen, applyDataset, directory } = useWorkbench()
  const [mode, setMode] = useState<Mode>('Server-Pfad')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  const close = () => setDataDialogOpen(false)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const finish = (dir: string, count: number, note?: string) => {
    applyDataset(dir, count)
    if (note) { setInfo(note); setError('') } else close()
  }

  // ── Server-Pfad ──
  const [path, setPath] = useState(directory)
  const scanPath = async () => {
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
      finish(ds.directory, ds.file_count, `${ds.file_count} XML-Dateien geladen${errs}. „Schließen", um zu prüfen.`)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  // ── Vorliegende Daten ──
  const [sources, setSources] = useState<Datasource[] | null>(null)
  useEffect(() => {
    if (mode === 'Vorliegende Daten' && sources === null) {
      dataApi.datasources().then(setSources).catch((e) => setError(String(e)))
    }
  }, [mode, sources])
  const pickSource = async (s: Datasource) => {
    setBusy(true); setError(''); setInfo('')
    try {
      const ds = await dataApi.scan(s.path)
      finish(ds.directory, ds.file_count)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  // ── Datenbank (wbdb) ──
  const [dbResources, setDbResources] = useState<WbdbResource[] | null>(null)
  const [selectedResources, setSelectedResources] = useState<string[]>([])
  useEffect(() => {
    if (mode === 'Datenbank' && dbResources === null) {
      dataApi.dbResources().then(setDbResources).catch((e) => setError(String(e)))
    }
  }, [mode, dbResources])
  const toggleResource = (id: string) => {
    setSelectedResources((prev) => (prev.includes(id) ? prev.filter((r) => r !== id) : [...prev, id]))
  }
  const loadDbSelection = async () => {
    if (selectedResources.length === 0) return
    setBusy(true); setError(''); setInfo('')
    try {
      const ds = await dataApi.loadDbResource(selectedResources)
      finish(ds.directory, ds.file_count, `${ds.file_count} Artikel aus der Datenbank geladen. „Schließen", um zu prüfen.`)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  return (
    <div onClick={close} style={{
      position: 'absolute', inset: 0, zIndex: 200, background: 'rgba(8,12,10,0.42)', backdropFilter: 'blur(1.5px)',
      display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: '8%',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 560, maxWidth: '90%', background: 'var(--lt-bg-2)', border: '1px solid var(--lt-line-2)',
        borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-pop)', overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', background: 'var(--lt-bg-0)', borderBottom: '1px solid var(--lt-line-1)' }}>
          <Icon name="folder" size={15} style={{ color: 'var(--lt-primary)' }} />
          <span style={{ fontSize: 14, fontWeight: 600, flex: 1 }}>Daten wählen</span>
          <Icon name="x" size={14} style={{ cursor: 'pointer', color: 'var(--lt-fg-3)' }} onClick={close} />
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Segmented options={['Server-Pfad', 'Upload', 'Vorliegende Daten', 'Datenbank']} value={mode} onChange={(v) => { setMode(v as Mode); setError(''); setInfo('') }} />

          {mode === 'Server-Pfad' && (
            <div style={card}>
              <div style={{ fontSize: 12, color: 'var(--lt-fg-3)', marginBottom: 8 }}>Pfad zu einem XML-Verzeichnis auf dem Server.</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input value={path} onChange={(e) => setPath(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && scanPath()} placeholder="/pfad/zu/xml" style={inputStyle} />
                <button onClick={scanPath} disabled={busy || !path.trim()} style={btnPrimary}>{busy ? '…' : 'Laden'}</button>
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

          {mode === 'Vorliegende Daten' && (
            <div style={{ ...card, padding: 8 }}>
              {sources === null ? <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)' }}>Lädt…</div>
                : sources.length === 0 ? <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)' }}>Keine Datenquellen konfiguriert (datasources.json).</div>
                : sources.map((s) => (
                  <button key={s.key} onClick={() => s.exists && pickSource(s)} disabled={busy || !s.exists} style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', textAlign: 'left',
                    background: 'transparent', border: 'none', borderRadius: 'var(--lt-r-sm)', cursor: s.exists ? 'pointer' : 'default',
                    color: s.exists ? 'var(--lt-fg-1)' : 'var(--lt-fg-4)',
                  }}>
                    <Icon name="book" size={15} style={{ color: s.exists ? 'var(--lt-primary)' : 'var(--lt-fg-4)' }} />
                    <span style={{ flex: 1, fontSize: 13 }}>{s.name}</span>
                    <span style={{ fontSize: 10, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-4)' }}>{s.exists ? s.path : 'nicht gefunden'}</span>
                  </button>
                ))}
            </div>
          )}

          {mode === 'Datenbank' && (
            <div style={{ ...card, padding: 8 }}>
              {dbResources === null ? <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)' }}>Lädt…</div>
                : dbResources.length === 0 ? <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)' }}>Keine Wörterbücher freigegeben.</div>
                : <>
                  {dbResources.map((r) => (
                    <label key={r.resource_id} style={{
                      width: '100%', boxSizing: 'border-box', display: 'flex', alignItems: 'center', gap: 10,
                      padding: '9px 10px', cursor: 'pointer', borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)',
                    }}>
                      <input type="checkbox" checked={selectedResources.includes(r.resource_id)} onChange={() => toggleResource(r.resource_id)} />
                      <Icon name="book" size={15} style={{ color: 'var(--lt-primary)' }} />
                      <span style={{ flex: 1, fontSize: 13 }}>{r.resource_id}</span>
                      <span style={{ fontSize: 10, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-4)' }}>{r.article_count} Artikel</span>
                    </label>
                  ))}
                  <div style={{ padding: '8px 2px 2px' }}>
                    <button onClick={loadDbSelection} disabled={busy || selectedResources.length === 0} style={{ ...btnPrimary, width: '100%' }}>
                      {busy ? '…' : `Laden${selectedResources.length ? ` (${selectedResources.length})` : ''}`}
                    </button>
                  </div>
                </>}
            </div>
          )}

          {error && <div style={{ fontSize: 12, color: 'var(--lt-err)' }}>{error}</div>}
          {info && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ flex: 1, fontSize: 12, color: 'var(--lt-primary)' }}>{info}</span>
              <button onClick={close} style={btnPrimary}>Schließen</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
