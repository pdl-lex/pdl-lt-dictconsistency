import { useState, type CSSProperties, type FormEvent } from 'react'
import { Icon, Logo } from '../design/icons'
import { useAuth } from '../state/auth'

const inputStyle: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '9px 10px', fontSize: 13,
  background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', outline: 'none',
}
const btnPrimary: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
  background: 'var(--lt-primary)', color: 'var(--lt-on-primary)', border: '1px solid var(--lt-primary)',
  height: 36, padding: '0 14px', borderRadius: 'var(--lt-r-md)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
}

export function LoginGate() {
  const { login, error } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setBusy(true)
    try {
      await login(username.trim(), password)
    } catch {
      /* error steht im Context */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{
      width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--lt-bg-1)', color: 'var(--lt-fg-1)',
    }}>
      <form onSubmit={submit} style={{
        width: 340, maxWidth: '90%', background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-2)',
        borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-pop)', padding: 24,
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <Logo size={22} />
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>LexoTerm Tools</div>
            <div style={{ fontSize: 11.5, color: 'var(--lt-fg-3)' }}>Wörterbuchkonsistenzprüfung</div>
          </div>
        </div>

        <label style={{ fontSize: 12, color: 'var(--lt-fg-3)', display: 'flex', flexDirection: 'column', gap: 5 }}>
          Benutzername
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" style={inputStyle} />
        </label>
        <label style={{ fontSize: 12, color: 'var(--lt-fg-3)', display: 'flex', flexDirection: 'column', gap: 5 }}>
          Passwort
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" style={inputStyle} />
        </label>

        {error && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--lt-err)' }}>
            <Icon name="x" size={12} /> {error}
          </div>
        )}

        <button type="submit" disabled={busy || !username.trim() || !password} style={btnPrimary}>
          {busy ? 'Meldet an…' : 'Anmelden'}
        </button>
      </form>
    </div>
  )
}
