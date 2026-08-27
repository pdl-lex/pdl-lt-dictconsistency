// Admin-Bereich: lokale Nutzerverwaltung (anlegen, Passwort zurücksetzen,
// aktiv/inaktiv schalten, wbdb_principal_id zuordnen) + „Testen"-Knopf gegen
// auth.current_scope. Verwaltet ausschließlich lokale Accounts — Principals
// und Freigaben in wbdb bleiben vollständig extern (siehe Plan Phase 4 /
// setup/Readme Access WBDB.md §2, „keine zweite Rechteverwaltung").
import { useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react'
import { Icon, type IconName } from '../design/icons'
import { adminApi, type AdminUser, type Principal, type ScopeResult } from '../api/client'
import { useAuth } from '../state/auth'
import type { LayoutMode } from '../state/workbench'

const card: CSSProperties = {
  background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-1)', padding: 14,
}
const inputStyle: CSSProperties = {
  boxSizing: 'border-box', padding: '7px 9px', fontSize: 12.5,
  background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', outline: 'none',
}
const btnPrimary: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
  background: 'var(--lt-primary)', color: 'var(--lt-on-primary)', border: '1px solid var(--lt-primary)',
  height: 30, padding: '0 12px', borderRadius: 'var(--lt-r-sm)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
}
const btnGhost: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
  background: 'var(--lt-bg-1)', color: 'var(--lt-fg-1)', border: '1px solid var(--lt-line-1)',
  height: 30, padding: '0 10px', borderRadius: 'var(--lt-r-sm)', fontSize: 12, cursor: 'pointer',
}
function badge(color: string): CSSProperties {
  return {
    fontSize: 10.5, fontWeight: 700, padding: '1px 7px', borderRadius: 'var(--lt-r-xs)',
    background: `color-mix(in srgb, ${color} 15%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
  }
}

function Callout({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <div style={{
      display: 'flex', gap: 10, padding: '11px 13px', fontSize: 12.5, lineHeight: 1.55,
      background: 'var(--lt-primary-soft)', border: '1px solid var(--lt-primary-line)',
      borderRadius: 'var(--lt-r-md)', color: 'var(--lt-fg-1)',
    }}>
      <Icon name={icon} size={14} style={{ color: 'var(--lt-primary)', flexShrink: 0, marginTop: 2 }} />
      <div style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{children}</div>
    </div>
  )
}

function PrincipalField({
  value, onChange, principals, principalsAvailable, style,
}: {
  value: string
  onChange: (value: string) => void
  principals: Principal[]
  principalsAvailable: boolean
  style?: CSSProperties
}) {
  if (!principalsAvailable) {
    return (
      <input value={value} onChange={(e) => onChange(e.target.value)}
        placeholder="wbdb-Principal (leer = kein Zugriff)"
        style={{ ...inputStyle, fontFamily: 'var(--lt-font-mono)', ...style }} />
    )
  }
  const known = !value || principals.some((p) => p.principal_id === value)
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      style={{ ...inputStyle, fontFamily: 'var(--lt-font-mono)', ...style }}>
      <option value="">— kein Principal —</option>
      {!known && <option value={value}>⚠ {value} (nicht in der aktuellen wbdb-Liste)</option>}
      {principals.map((p) => (
        <option key={p.principal_id} value={p.principal_id}>
          {p.label} — {p.principal_id} ({p.kind}{!p.active ? ', inaktiv' : ''})
        </option>
      ))}
    </select>
  )
}

export function AdminConfig() {
  return (
    <div className="cfg-scroll" style={{ overflowY: 'auto', flex: 1, background: 'var(--lt-bg-2)', padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Callout icon="shield">
        Diese App legt keine wbdb-Principals an und schreibt keine Freigaben — das bleibt
        vollständig Sache von wbdb. Hier wird einem lokalen Account nur eine dort bereits
        existierende <code>principal_id</code> zugeordnet.
      </Callout>
      <Callout icon="flask">
        „Testen" zeigt live, was eine <code>principal_id</code> gerade in wbdb sehen darf
        (<code>auth.current_scope</code>) — rein lesend, deckt Tippfehler bei der Zuordnung
        sofort auf.
      </Callout>
      <Callout icon="user">
        Fehlt für einen neuen Account die passende Freigabe in wbdb, muss sie extern bei
        wer auch immer wbdb administriert angefragt werden — die Zuordnung hier setzt nur
        eine bereits existierende <code>principal_id</code> ein.
      </Callout>
    </div>
  )
}

export function AdminConfigPane({ layout }: { layout: LayoutMode }) {
  return (
    <section style={{
      gridArea: 'cfg', background: 'var(--lt-bg-0)',
      borderRight: layout === 'left' ? '1px solid var(--lt-line-1)' : 'none',
      borderLeft: layout === 'right' ? '1px solid var(--lt-line-1)' : 'none',
      borderBottom: layout === 'bottom' ? '1px solid var(--lt-line-1)' : 'none',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ padding: '14px 18px 12px', background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
        <div className="lt-eyebrow" style={{ marginBottom: 4 }}>Verwaltung</div>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Admin-Bereich</h2>
        <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12, lineHeight: 1.45 }}>
          Lokale Accounts anlegen, Passwörter zurücksetzen, wbdb-Principal zuordnen.
        </p>
      </div>
      <AdminConfig />
    </section>
  )
}

export function AdminMain() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [error, setError] = useState('')
  const [principals, setPrincipals] = useState<Principal[]>([])
  const [principalsAvailable, setPrincipalsAvailable] = useState(true)
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [busyId, setBusyId] = useState<number | null>(null)

  const [resetOpenId, setResetOpenId] = useState<number | null>(null)
  const [resetDrafts, setResetDrafts] = useState<Record<number, string>>({})
  const [resetBusy, setResetBusy] = useState(false)
  const [resetError, setResetError] = useState('')

  const [testOpenId, setTestOpenId] = useState<number | null>(null)
  const [testBusy, setTestBusy] = useState(false)
  const [testResult, setTestResult] = useState<ScopeResult | null>(null)
  const [testError, setTestError] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ username: '', password: '', principal: '', isAdmin: false })
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState('')

  const refresh = async () => {
    try {
      const list = await adminApi.listUsers()
      setUsers(list)
      setDrafts(Object.fromEntries(list.map((u) => [u.id, u.wbdb_principal_id ?? ''])))
    } catch (e) { setError(String(e)) }
  }
  const refreshPrincipals = async () => {
    try { setPrincipals(await adminApi.listPrincipals()); setPrincipalsAvailable(true) }
    catch { setPrincipals([]); setPrincipalsAvailable(false) }
  }
  useEffect(() => { void refresh(); void refreshPrincipals() }, [])

  const savePrincipal = async (id: number) => {
    setBusyId(id); setError('')
    try { await adminApi.updateUser(id, { wbdb_principal_id: drafts[id] || null }); await refresh() }
    catch (e) { setError(String(e)) } finally { setBusyId(null) }
  }
  const toggleActive = async (u: AdminUser) => {
    setBusyId(u.id); setError('')
    try { await adminApi.updateUser(u.id, { active: !u.active }); await refresh() }
    catch (e) { setError(String(e)) } finally { setBusyId(null) }
  }
  const toggleAdmin = async (u: AdminUser) => {
    setBusyId(u.id); setError('')
    try { await adminApi.updateUser(u.id, { is_admin: !u.is_admin }); await refresh() }
    catch (e) { setError(String(e)) } finally { setBusyId(null) }
  }

  const toggleReset = (id: number) => {
    setResetError('')
    setResetOpenId((cur) => (cur === id ? null : id))
  }
  const submitReset = async (id: number) => {
    setResetBusy(true); setResetError('')
    try {
      await adminApi.resetPassword(id, resetDrafts[id] ?? '')
      setResetOpenId(null)
      setResetDrafts((d) => ({ ...d, [id]: '' }))
    } catch (e) { setResetError(String(e)) } finally { setResetBusy(false) }
  }

  const toggleTest = async (id: number, principal: string) => {
    if (testOpenId === id) { setTestOpenId(null); return }
    setTestOpenId(id); setTestResult(null); setTestError('')
    if (!principal.trim()) { setTestError('Kein Principal eingetragen.'); return }
    setTestBusy(true)
    try { setTestResult(await adminApi.testPrincipal(principal.trim())) }
    catch (e) { setTestError(String(e)) } finally { setTestBusy(false) }
  }

  const submitCreate = async (e: FormEvent) => {
    e.preventDefault()
    setCreateBusy(true); setCreateError('')
    try {
      await adminApi.createUser(form.username.trim(), form.password, form.principal.trim(), form.isAdmin)
      setForm({ username: '', password: '', principal: '', isAdmin: false })
      setShowCreate(false)
      await refresh()
    } catch (e) { setCreateError(String(e)) } finally { setCreateBusy(false) }
  }

  return (
    <main className="agm-grid" style={{ gridArea: 'main', overflowY: 'auto', background: 'var(--lt-bg-1)', padding: '18px 20px' }}>
      <div style={{ maxWidth: 900, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div className="lt-eyebrow" style={{ marginBottom: 4 }}>Verwaltung</div>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Nutzerverwaltung</h2>
            <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12.5, lineHeight: 1.5 }}>
              Lokale Accounts dieser App — unabhängig von wbdb-Principals/-Grants.
            </p>
          </div>
          <button onClick={() => setShowCreate((v) => !v)} style={btnPrimary}>
            <Icon name="plus" size={12} /> Neuer Nutzer
          </button>
        </div>

        {showCreate && (
          <form onSubmit={submitCreate} style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11.5, color: 'var(--lt-fg-3)' }}>
                Benutzername
                <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                  autoFocus style={{ ...inputStyle, width: 180 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11.5, color: 'var(--lt-fg-3)' }}>
                Passwort
                <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                  style={{ ...inputStyle, width: 180 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11.5, color: 'var(--lt-fg-3)' }}>
                wbdb-Principal (optional)
                <PrincipalField value={form.principal} onChange={(v) => setForm({ ...form, principal: v })}
                  principals={principals} principalsAvailable={principalsAvailable} style={{ width: 180 }} />
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--lt-fg-2)', alignSelf: 'flex-end', paddingBottom: 8 }}>
                <input type="checkbox" checked={form.isAdmin} onChange={(e) => setForm({ ...form, isAdmin: e.target.checked })} />
                Administrator
              </label>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button type="submit" disabled={createBusy || !form.username.trim() || !form.password} style={btnPrimary}>
                {createBusy ? '…' : 'Anlegen'}
              </button>
              <button type="button" onClick={() => setShowCreate(false)} style={btnGhost}>Abbrechen</button>
              {createError && <span style={{ fontSize: 12, color: 'var(--lt-err)' }}>{createError}</span>}
            </div>
          </form>
        )}

        {error && <div style={{ fontSize: 12.5, color: 'var(--lt-err)' }}>{error}</div>}
        {!principalsAvailable && (
          <div style={{ fontSize: 12, color: 'var(--lt-fg-3)' }}>
            wbdb nicht erreichbar — Principal wird als Freitext eingegeben, ohne Abgleich mit der vorhandenen Liste.
          </div>
        )}

        <div style={{ ...card, padding: 0 }}>
          {users === null ? (
            <div style={{ padding: 16, fontSize: 12.5, color: 'var(--lt-fg-3)' }}>Lädt…</div>
          ) : users.length === 0 ? (
            <div style={{ padding: 16, fontSize: 12.5, color: 'var(--lt-fg-3)' }}>Keine lokalen Nutzer.</div>
          ) : users.map((u) => {
            const isSelf = u.id === currentUser?.id
            const draft = drafts[u.id] ?? ''
            const dirty = draft !== (u.wbdb_principal_id ?? '')
            return (
              <div key={u.id} style={{ borderBottom: '1px solid var(--lt-line-1)', padding: '10px 12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <Icon name="user" size={13} style={{ color: 'var(--lt-fg-4)' }} />
                  <span style={{ fontSize: 13, fontWeight: 600, minWidth: 100 }}>{u.username}</span>
                  {u.is_admin && <span style={badge('var(--lt-primary)')}>Admin</span>}
                  {!u.active && <span style={badge('var(--lt-err)')}>Inaktiv</span>}
                  {isSelf && <span style={{ fontSize: 10.5, color: 'var(--lt-fg-4)' }}>(Sie)</span>}
                  <span style={{ flex: 1 }} />
                  <PrincipalField value={draft} onChange={(v) => setDrafts((d) => ({ ...d, [u.id]: v }))}
                    principals={principals} principalsAvailable={principalsAvailable} style={{ width: 220 }} />
                  {dirty && (
                    <button onClick={() => savePrincipal(u.id)} disabled={busyId === u.id} style={btnPrimary}>
                      {busyId === u.id ? '…' : 'Speichern'}
                    </button>
                  )}
                  <button onClick={() => void toggleTest(u.id, draft)} style={btnGhost}>
                    <Icon name="flask" size={12} /> Testen
                  </button>
                  <button onClick={() => toggleReset(u.id)} style={btnGhost}>Passwort</button>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11.5, color: 'var(--lt-fg-3)' }}
                    title={isSelf ? 'Der eigene Account kann nicht deaktiviert werden.' : undefined}>
                    <input type="checkbox" checked={u.active} disabled={isSelf || busyId === u.id} onChange={() => void toggleActive(u)} /> aktiv
                  </label>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11.5, color: 'var(--lt-fg-3)' }}
                    title={isSelf ? 'Die eigene Admin-Rolle kann nicht entzogen werden.' : undefined}>
                    <input type="checkbox" checked={u.is_admin} disabled={isSelf || busyId === u.id} onChange={() => void toggleAdmin(u)} /> Admin
                  </label>
                </div>

                {resetOpenId === u.id && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                    <input type="password" value={resetDrafts[u.id] ?? ''}
                      onChange={(e) => setResetDrafts((d) => ({ ...d, [u.id]: e.target.value }))}
                      placeholder="Neues Passwort" style={{ ...inputStyle, width: 220 }} />
                    <button onClick={() => submitReset(u.id)} disabled={resetBusy || !(resetDrafts[u.id] ?? '')} style={btnPrimary}>
                      {resetBusy ? '…' : 'Setzen'}
                    </button>
                    {resetError && <span style={{ fontSize: 11.5, color: 'var(--lt-err)' }}>{resetError}</span>}
                  </div>
                )}

                {testOpenId === u.id && (
                  <div style={{
                    marginTop: 8, padding: 10, background: 'var(--lt-bg-2)',
                    border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-sm)', fontSize: 11.5,
                  }}>
                    {testBusy ? 'Testet…'
                      : testError ? <span style={{ color: 'var(--lt-err)' }}>{testError}</span>
                      : testResult && testResult.scope.length === 0 ? 'Keine Freigaben für diesen Principal — leeres Ergebnis, kein Fehler.'
                      : testResult && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontFamily: 'var(--lt-font-mono)' }}>
                          {testResult.scope.map((row, i) => (
                            <div key={i}>{Object.entries(row).map(([k, v]) => `${k}=${String(v)}`).join('  ')}</div>
                          ))}
                        </div>
                      )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </main>
  )
}
