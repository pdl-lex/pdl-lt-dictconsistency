import { useEffect, useState, type CSSProperties } from 'react'
import { Header } from './layout/Header'
import { Rail } from './layout/Rail'
import { ConfigPane } from './layout/ConfigPane'
import { ResultsPane } from './layout/ResultsPane'
import { StatusBar } from './layout/StatusBar'
import { CommandPalette } from './layout/CommandPalette'
import { DataDialog } from './layout/DataDialog'
import { LoginDialog } from './layout/LoginDialog'
import { AdminConfigPane, AdminMain } from './layout/AdminView'
import { MobileWorkbench } from './layout/Mobile'
import { ApiInfoConfigPane, ApiInfoMain } from './modules/apiInfo'
import { IntroConfigPane, IntroMain } from './modules/intro'
import { StructureConfigPane, StructureMain, StructureProvider, useStructure } from './modules/structure'
import { useIsMobile } from './design/useIsMobile'
import { AuthProvider, useAuth } from './state/auth'
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
  const { layout, railPinned, run, dataDialogOpen, loginDialogOpen, activeId } = useWorkbench()
  const structure = useStructure()
  const [cmdOpen, setCmdOpen] = useState(false)
  const isMobile = useIsMobile()
  const railW = railPinned ? 248 : 56
  const isApi = activeId === 'api'
  const isAdmin = activeId === 'admin'
  const isStructure = activeId === 'structure'
  const isIntro = activeId === 'intro'

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setCmdOpen((v) => !v) }
      else if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        if (isStructure) void structure.analyze()
        else if (!isApi && !isAdmin && !isIntro) run()
      }
      else if (e.key === 'Escape') setCmdOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [run, isApi, isAdmin, isIntro, isStructure, structure])

  if (isMobile) {
    return (
      <>
        <MobileWorkbench />
        {dataDialogOpen && <DataDialog />}
        {loginDialogOpen && <LoginDialog />}
      </>
    )
  }

  return (
    <div style={{
      color: 'var(--lt-fg-1)', background: 'var(--lt-bg-1)', width: '100%', height: '100%',
      display: 'grid', transition: 'grid-template-columns .18s ease', ...gridFor(layout, railW),
    }}>
      <Header onOpenPalette={() => setCmdOpen(true)} />
      <Rail />
      {isAdmin ? <AdminConfigPane layout={layout} /> : isApi ? <ApiInfoConfigPane layout={layout} /> : isStructure ? <StructureConfigPane layout={layout} /> : isIntro ? <IntroConfigPane layout={layout} /> : <ConfigPane layout={layout} />}
      {isAdmin ? <AdminMain /> : isApi ? <ApiInfoMain /> : isStructure ? <StructureMain /> : isIntro ? <IntroMain /> : <ResultsPane />}
      <StatusBar />
      {cmdOpen && <CommandPalette onClose={() => setCmdOpen(false)} />}
      {dataDialogOpen && <DataDialog />}
      {loginDialogOpen && <LoginDialog />}
    </div>
  )
}

function Gate() {
  const { loading } = useAuth()
  if (loading) return <div style={{ width: '100%', height: '100%', background: 'var(--lt-bg-1)' }} />
  return (
    <WorkbenchProvider>
      <StructureProvider>
        <Workbench />
      </StructureProvider>
    </WorkbenchProvider>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}
