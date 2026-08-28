// Datei-Vorschau für Ergebniszeilen: öffnet die geprüfte XML-Datei serverseitig,
// zeigt sie zeilennummeriert an und springt zur/markiert die Fundstelle.
// Nachbau des Reflex-v1-Verhaltens (XmlPreviewState in components.py).
import { useEffect, useRef, useState } from 'react'
import { ApiError, dataApi } from '../api/client'
import { Icon } from '../design/icons'

export interface FilePreviewTarget {
  directory: string
  subdir: string
  filename: string
  line: number
}

export function FilePreviewDialog({ target, onClose }: { target: FilePreviewTarget; onClose: () => void }) {
  const { directory, subdir, filename, line } = target
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    setContent(null)
    setError('')
    dataApi.fileContent(directory, subdir, filename)
      .then((r) => { if (!cancelled) setContent(r.content) })
      .catch((e) => { if (!cancelled) setError(e instanceof ApiError ? e.message : 'Fehler beim Öffnen der Datei.') })
    return () => { cancelled = true }
  }, [directory, subdir, filename])

  useEffect(() => {
    if (content == null) return
    const el = containerRef.current?.querySelector('#lt-preview-highlight')
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [content])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const lines = content != null ? content.split('\n') : []
  const numWidth = String(lines.length).length

  return (
    <div onClick={onClose} style={{
      position: 'absolute', inset: 0, zIndex: 200, background: 'rgba(8,12,10,0.42)', backdropFilter: 'blur(1.5px)',
      display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: '6%',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 900, maxWidth: '90%', background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-2)',
        borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-pop)', padding: 24,
        display: 'flex', flexDirection: 'column', gap: 12, maxHeight: '80vh',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Icon name="file" size={16} style={{ color: 'var(--lt-fg-3)' }} />
          <div style={{ fontSize: 15, fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {filename}
          </div>
          <Icon name="x" size={14} style={{ cursor: 'pointer', color: 'var(--lt-fg-3)' }} onClick={onClose} />
        </div>

        <div style={{ fontSize: 12.5, color: 'var(--lt-fg-3)' }}>
          Treffer in Zeile: <span style={{ fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-1)' }}>{line}</span>
        </div>

        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', fontSize: 12.5,
            background: 'var(--lt-err-soft)', border: '1px solid var(--lt-err-line)', borderRadius: 'var(--lt-r-sm)',
            color: 'var(--lt-err)',
          }}>{error}</div>
        )}

        <div ref={containerRef} style={{
          flex: 1, minHeight: 200, overflow: 'auto', background: 'var(--lt-bg-1)',
          border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-sm)', padding: '10px 0',
          fontFamily: 'var(--lt-font-mono)', fontSize: 12, lineHeight: 1.55,
        }}>
          {content == null && !error && (
            <div style={{ padding: '20px 16px', color: 'var(--lt-fg-3)' }}>Lädt…</div>
          )}
          {lines.map((text, i) => {
            const num = i + 1
            const isHit = num === line
            return (
              <div key={num} id={isHit ? 'lt-preview-highlight' : undefined} style={{
                display: 'flex', padding: '0 12px',
                background: isHit ? 'var(--lt-warn-soft)' : 'transparent',
                borderLeft: isHit ? '3px solid var(--lt-warn)' : '3px solid transparent',
              }}>
                <span style={{
                  color: 'var(--lt-fg-4)', userSelect: 'none', flexShrink: 0,
                  width: `${numWidth}ch`, textAlign: 'right', marginRight: '1em',
                }}>{num}</span>
                <span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{text || ' '}</span>
              </div>
            )
          })}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            display: 'inline-flex', alignItems: 'center', gap: 7, background: 'var(--lt-primary)', color: 'var(--lt-on-primary)',
            border: '1px solid var(--lt-primary)', height: 34, padding: '0 16px', borderRadius: 'var(--lt-r-md)',
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}>Schließen</button>
        </div>
      </div>
    </div>
  )
}
