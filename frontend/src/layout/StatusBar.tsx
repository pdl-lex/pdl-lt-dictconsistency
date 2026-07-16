import type { ReactNode } from 'react'
import { Kbd, kc } from '../design/widgets'
import { useWorkbench } from '../state/workbench'

function Item({ dot, k, v }: { dot?: string; k?: string; v: ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 10px', height: 32, borderRight: '1px solid var(--lt-line-1)' }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: 3, background: dot }} />}
      {k && <span style={{ color: 'var(--lt-fg-4)' }}>{k}</span>}
      <span>{v}</span>
    </div>
  )
}

export function StatusBar() {
  const { directory, fileCount, result, lastRunMs } = useWorkbench()
  const files = result ? String(result.files_checked) : fileCount != null ? String(fileCount) : '–'
  return (
    <footer style={{
      gridArea: 'stat', display: 'flex', alignItems: 'center', background: 'var(--lt-bg-0)',
      borderTop: '1px solid var(--lt-line-1)', fontSize: 11, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)',
    }}>
      <Item dot={directory ? 'var(--lt-primary)' : 'var(--lt-warn)'} k="Daten:" v={directory || 'nicht gesetzt'} />
      <Item k="Dateien:" v={files} />
      <Item dot="var(--lt-warn)" k="LLM:" v="nicht konfiguriert" />
      <Item k="Letzter Lauf:" v={lastRunMs != null ? `${(lastRunMs / 1000).toFixed(2)} s` : '–'} />
      <span style={{ flex: 1 }} />
      <Item v="UTF-8" />
      <Item v="TL0" />
      <Item v="DE" />
      <span style={{ padding: '0 12px', color: 'var(--lt-fg-4)' }}>
        <Kbd>{kc('K')}</Kbd> Befehle
      </span>
    </footer>
  )
}
