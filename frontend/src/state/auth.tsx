// Anmeldezustand: lädt GET /api/auth/me beim Mount (Cookie-Session), stellt
// login()/logout() bereit. Getrennt von workbench.tsx, da unabhängig von
// Modul/Layout-Zustand — App.tsx gated Workbench dahinter.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, authApi, type User } from '../api/client'

interface AuthState {
  user: User | null
  loading: boolean
  error: string
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    authApi.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setError('')
    try {
      setUser(await authApi.login(username, password))
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? 'Benutzername oder Passwort falsch.' : String(e))
      throw e
    }
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout().catch(() => {})
    setUser(null)
  }, [])

  const value = useMemo<AuthState>(() => ({ user, loading, error, login, logout }), [user, loading, error, login, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used within AuthProvider')
  return v
}
