// Zentraler Workbench-Zustand: Layout, Theme, aktives Modul, Datenpfad,
// Konfiguration je Modul und Prüf-Ausführung gegen die API.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { CheckResult } from '../api/client'
import { ApiError } from '../api/client'
import { MODULES, defaultConfig, moduleById, type Config, type JobProgress, type ModuleDef, type TagAttrPair } from '../modules/registry'

export type LayoutMode = 'left' | 'right' | 'bottom'

interface WorkbenchState {
  theme: 'light' | 'dark'
  toggleTheme: () => void
  layout: LayoutMode
  setLayout: (l: LayoutMode) => void
  railPinned: boolean
  setRailPinned: (v: boolean) => void
  activeId: string
  setActiveId: (id: string) => void
  module: ModuleDef
  directory: string
  setDirectory: (d: string) => void
  fileCount: number | null
  applyDataset: (directory: string, fileCount: number) => void
  dataDialogOpen: boolean
  setDataDialogOpen: (v: boolean) => void
  loginDialogOpen: boolean
  setLoginDialogOpen: (v: boolean) => void
  config: Config
  setField: (key: string, value: string | boolean | string[] | TagAttrPair[]) => void
  result: CheckResult | null
  running: boolean
  error: string
  lastRunMs: number | null
  progress: JobProgress | null
  run: () => Promise<void>
}

const Ctx = createContext<WorkbenchState | null>(null)

export function WorkbenchProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  const [layout, setLayout] = useState<LayoutMode>('left')
  const [railPinned, setRailPinned] = useState(false)
  const [activeId, setActiveId] = useState<string>('intro')
  const [directory, setDirectory] = useState<string>(() => localStorage.getItem('lt.directory') ?? '')
  const [fileCount, setFileCount] = useState<number | null>(null)
  const [dataDialogOpen, setDataDialogOpen] = useState(false)
  const [loginDialogOpen, setLoginDialogOpen] = useState(false)
  const [configs, setConfigs] = useState<Record<string, Config>>({})
  const [result, setResult] = useState<CheckResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [lastRunMs, setLastRunMs] = useState<number | null>(null)
  const [progress, setProgress] = useState<JobProgress | null>(null)

  const module = moduleById(activeId) ?? MODULES[0]
  const config = configs[activeId] ?? defaultConfig(module)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => { localStorage.setItem('lt.directory', directory) }, [directory])

  const setField = useCallback((key: string, value: string | boolean | string[] | TagAttrPair[]) => {
    setConfigs((prev) => {
      const base = prev[activeId] ?? defaultConfig(module)
      return { ...prev, [activeId]: { ...base, [key]: value } }
    })
  }, [activeId, module])

  const changeModule = useCallback((id: string) => {
    setActiveId(id)
    setResult(null)
    setError('')
    setProgress(null)
  }, [])

  const applyDataset = useCallback((dir: string, count: number) => {
    setDirectory(dir)
    setFileCount(count)
    setResult(null)
    setError('')
  }, [])

  const run = useCallback(async () => {
    if (!directory.trim()) { setError('Bitte zuerst ein Datenverzeichnis angeben.'); return }
    setRunning(true); setError(''); setProgress(null)
    try {
      const res = module.runJob
        ? await module.runJob(directory, config, setProgress)
        : await module.run!(directory, config)
      setResult(res)
      setLastRunMs(res.duration_ms)
    } catch (e) {
      setError(e instanceof ApiError ? `Fehler (${e.status}): ${e.message}` : String(e))
      setResult(null)
    } finally {
      setRunning(false)
      setProgress(null)
    }
  }, [directory, module, config])

  const value = useMemo<WorkbenchState>(() => ({
    theme, toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
    layout, setLayout, railPinned, setRailPinned,
    activeId, setActiveId: changeModule, module,
    directory, setDirectory, fileCount, applyDataset, dataDialogOpen, setDataDialogOpen,
    loginDialogOpen, setLoginDialogOpen,
    config, setField,
    result, running, error, lastRunMs, progress, run,
  }), [theme, layout, railPinned, activeId, changeModule, module, directory, fileCount, applyDataset, dataDialogOpen, loginDialogOpen, config, setField, result, running, error, lastRunMs, progress, run])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useWorkbench(): WorkbenchState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useWorkbench must be used within WorkbenchProvider')
  return v
}
