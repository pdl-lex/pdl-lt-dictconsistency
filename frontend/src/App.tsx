import { useEffect, useState, type CSSProperties } from 'react'
import { Header } from './layout/Header'
import { Rail } from './layout/Rail'
import { ConfigPane } from './layout/ConfigPane'
import { ResultsPane } from './layout/ResultsPane'
import { StatusBar } from './layout/StatusBar'
import { CommandPalette } from './layout/CommandPalette'
import { DataDialog } from './layout/DataDialog'
import { WorkbenchProvider, useWorkbench } from './state/workbench'

function gridFor(layout: string, railW: number): CSSProperties {
  if (layout === 'right') {
    return {
      gridTemplateColumns: `${railW}px 1fr 380px`,
      gridTemplateRows: '44px 1fr 32px',
      gridTemplateAreas: '"head head head" "rail main cfg" "stat stat stat"',
    }
  }
  if (layout === 'bottom') {
    return {
      gridTemplateColumns: `${railW}px 1fr`,
      gridTemplateRows: '44px minmax(280px, 42%) 1fr 32px',
      gridTemplateAreas: '"head head" "rail cfg" "rail main" "stat stat"',
    }
  }
  return {
    gridTemplateColumns: `${railW}px 380px 1fr`,
    gridTemplateRows: '44px 1fr 32px',
    gridTemplateAreas: '"head head head" "rail cfg main" "stat stat stat"',
  }
}

function Workbench() {
  const { layout, railPinned, run, dataDialogOpen } = useWorkbench()
  const [cmdOpen, setCmdOpen] = useState(false)
  const railW = railPinned ? 248 : 56

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setCmdOpen((v) => !v) }
      else if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); run() }
      else if (e.key === 'Escape') setCmdOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [run])

  return (
    <div style={{
      color: 'var(--lt-fg-1)', background: 'var(--lt-bg-1)', width: '100%', height: '100%',
      display: 'grid', transition: 'grid-template-columns .18s ease', ...gridFor(layout, railW),
    }}>
      <Header onOpenPalette={() => setCmdOpen(true)} />
      <Rail />
      <ConfigPane layout={layout} />
      <ResultsPane />
      <StatusBar />
      {cmdOpen && <CommandPalette onClose={() => setCmdOpen(false)} />}
      {dataDialogOpen && <DataDialog />}
    </div>
  )
}

export default function App() {
  return (
    <WorkbenchProvider>
      <Workbench />
    </WorkbenchProvider>
  )
}
