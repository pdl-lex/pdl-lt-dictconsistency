// Mobil-Ansicht (≤640px): das Workbench-Layout als vertikal gestapelte,
// scrollbare Spalte nach Design-Handoff (variant-b-mobile / mobile-shared).
// Header (Hamburger + „Prüfen") → Parameter-Pane → Ergebnisse (Statistik-
// Akkordeon + Kartenliste) → Statuszeile; Menü als Slide-in-Modal von links
// (Navigation + Layout-Reihenfolge + Dunkler Modus).
import { useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { Icon, Logo, type IconName } from '../design/icons'
import { Diff, HBar, Sparkbars, type SparkDatum } from '../design/widgets'
import { ApiInfoConfig, ApiInfoMain } from '../modules/apiInfo'
import { IntroConfig, IntroMain } from '../modules/intro'
import { StructureConfig, StructureMain, useStructure } from '../modules/structure'
import { ArtikelsucheConfig, ArtikelsucheMain } from '../modules/artikelsuche'
import { AdminConfig, AdminMain } from './AdminView'
import type { Column } from '../modules/registry'
import { useAuth } from '../state/auth'
import { useWorkbench } from '../state/workbench'
import { DataCard, FieldRenderer } from './ConfigPane'
import { buildMenu } from './Rail'
import { aggregate, PHASE_LABELS, str, toCsv } from './ResultsPane'

const CARD_PAGE = 30

// ── Menü-Bausteine (Slide-in) ───────────────────────────────────────────────

function MenuLabel({ children }: { children: ReactNode }) {
  return <div className="lt-eyebrow" style={{ padding: '12px 18px 6px', fontSize: 10.5 }}>{children}</div>
}

function MenuRow({ icon, label, active, sub, onClick, indent, disabled }: {
  icon?: IconName; label: string; active?: boolean; sub?: ReactNode
  onClick?: () => void; indent?: boolean; disabled?: boolean
}) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      width: '100%', minHeight: 46, display: 'flex', alignItems: 'center', gap: 12,
      padding: indent ? '8px 18px 8px 46px' : '8px 18px',
      background: active ? 'var(--lt-primary-soft)' : 'transparent', border: 'none',
      borderLeft: active ? '3px solid var(--lt-primary)' : '3px solid transparent',
      color: disabled ? 'var(--lt-fg-4)' : active ? 'var(--lt-primary)' : 'var(--lt-fg-1)',
      cursor: disabled ? 'default' : 'pointer', textAlign: 'left', fontWeight: active ? 600 : 400,
    }}>
      {icon && <Icon name={icon} size={17} style={{ color: active ? 'var(--lt-primary)' : 'var(--lt-fg-3)' }} />}
      <span style={{ flex: 1, fontSize: 14.5 }}>{label}</span>
      {sub != null && <span style={{ fontSize: 11, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-4)' }}>{sub}</span>}
    </button>
  )
}

function MenuToggle({ label, on, onChange, icon }: {
  label: string; on: boolean; onChange: (v: boolean) => void; icon: IconName
}) {
  return (
    <button onClick={() => onChange(!on)} style={{
      width: '100%', minHeight: 46, display: 'flex', alignItems: 'center', gap: 12,
      padding: '8px 18px', background: 'transparent', border: 'none',
      borderLeft: '3px solid transparent', color: 'var(--lt-fg-1)', cursor: 'pointer', textAlign: 'left',
    }}>
      <Icon name={icon} size={17} style={{ color: 'var(--lt-fg-3)' }} />
      <span style={{ flex: 1, fontSize: 14.5 }}>{label}</span>
      <span style={{
        width: 40, height: 24, borderRadius: 12, position: 'relative', flexShrink: 0,
        background: on ? 'var(--lt-primary)' : 'var(--lt-line-2)', transition: 'background .15s',
      }}>
        <span style={{
          position: 'absolute', top: 2, left: on ? 18 : 2, width: 20, height: 20, borderRadius: 10,
          background: 'white', boxShadow: '0 1px 3px rgba(0,0,0,0.25)', transition: 'left .15s',
        }} />
      </span>
    </button>
  )
}

function MenuSegmented({ options, value, onChange }: {
  options: string[]; value: string; onChange: (v: string) => void
}) {
  return (
    <div style={{
      display: 'flex', gap: 4, padding: 3, margin: '2px 18px 8px',
      background: 'var(--lt-bg-2)', border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-md)',
    }}>
      {options.map((opt) => {
        const active = opt === value
        return (
          <button key={opt} onClick={() => onChange(opt)} style={{
            flex: 1, height: 36, border: 'none', cursor: 'pointer', fontSize: 12.5,
            fontWeight: active ? 600 : 500, borderRadius: 'var(--lt-r-sm)',
            background: active ? 'var(--lt-bg-0)' : 'transparent',
            color: active ? 'var(--lt-fg-1)' : 'var(--lt-fg-3)',
            boxShadow: active ? 'var(--lt-shadow-1)' : 'none',
          }}>{opt}</button>
        )
      })}
    </div>
  )
}

type Order = 'params' | 'results'

function MobileMenu({ open, onClose, order, setOrder }: {
  open: boolean; onClose: () => void; order: Order; setOrder: (o: Order) => void
}) {
  const { activeId, setActiveId, setDataDialogOpen, setLoginDialogOpen, theme, toggleTheme } = useWorkbench()
  const { user, logout } = useAuth()
  const menu = useMemo(() => buildMenu(!!user?.is_admin), [user])
  const activeGroup = menu.find((g) => g.items.some((it) => it.id === activeId))?.group ?? null
  const [openGroup, setOpenGroup] = useState<string | null>(activeGroup)

  const pick = (id: string) => {
    if (id === 'data') setDataDialogOpen(true)
    else setActiveId(id)
    onClose()
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 100, pointerEvents: open ? 'auto' : 'none' }}>
      <div onClick={onClose} style={{
        position: 'absolute', inset: 0, background: 'rgba(8,12,10,0.44)',
        opacity: open ? 1 : 0, transition: 'opacity .2s ease',
      }} />
      <div style={{
        position: 'absolute', top: 0, bottom: 0, left: 0, width: 316, maxWidth: '86%',
        background: 'var(--lt-bg-0)', borderRight: '1px solid var(--lt-line-1)',
        boxShadow: 'var(--lt-shadow-pop)', display: 'flex', flexDirection: 'column',
        transform: open ? 'translateX(0)' : 'translateX(-100%)',
        transition: 'transform .24s cubic-bezier(.4,0,.2,1)',
      }}>
        <div style={{
          height: 52, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10,
          padding: '0 8px 0 18px', borderBottom: '1px solid var(--lt-line-1)',
        }}>
          <Logo size={17} />
          <span style={{ flex: 1, fontSize: 15, fontWeight: 600 }}>LexoTerm Tools</span>
          <button onClick={onClose} aria-label="Schließen" style={{
            width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: 'transparent', border: 'none', color: 'var(--lt-fg-2)', cursor: 'pointer',
          }}>
            <Icon name="x" size={16} />
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '10px 0' }}>
          <MenuLabel>Navigation</MenuLabel>
          {menu.map((g) => {
            const hasActive = g.items.some((it) => it.id === activeId)
            const isOpen = openGroup === g.group
            return (
              <div key={g.group}>
                <MenuRow icon={g.icon} label={g.group} active={hasActive}
                  sub={isOpen ? '▾' : g.items.length}
                  onClick={() => setOpenGroup(isOpen ? null : g.group)} />
                {isOpen && g.items.map((it) => (
                  <MenuRow key={it.id} indent label={it.label} active={it.id === activeId}
                    disabled={it.disabled} onClick={() => !it.disabled && pick(it.id)} />
                ))}
              </div>
            )
          })}

          <div style={{ height: 1, background: 'var(--lt-line-1)', margin: '10px 0' }} />

          <MenuLabel>Layout</MenuLabel>
          <MenuSegmented
            options={['Parameter oben', 'Ergebnisse oben']}
            value={order === 'params' ? 'Parameter oben' : 'Ergebnisse oben'}
            onChange={(v) => setOrder(v === 'Parameter oben' ? 'params' : 'results')}
          />

          <MenuLabel>Darstellung</MenuLabel>
          <MenuToggle icon={theme === 'dark' ? 'moon' : 'sun'} label="Dunkler Modus"
            on={theme === 'dark'} onChange={() => toggleTheme()} />

          <div style={{ height: 1, background: 'var(--lt-line-1)', margin: '10px 0' }} />
          <MenuLabel>Konto</MenuLabel>
          {user ? (
            <>
              <MenuRow icon="user" label={user.username} />
              <MenuRow icon="logout" label="Abmelden" onClick={() => void logout()} />
            </>
          ) : (
            <MenuRow icon="user" label="Login" onClick={() => { onClose(); setLoginDialogOpen(true) }} />
          )}
        </div>
      </div>
    </div>
  )
}

// ── Parameter-Pane (gestapelt) ──────────────────────────────────────────────

function MobileParams() {
  const { module } = useWorkbench()
  return (
    <section style={{ background: 'var(--lt-bg-0)' }}>
      <div style={{ padding: '13px 16px 12px', background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
        <div className="lt-eyebrow" style={{ marginBottom: 3, fontSize: 10 }}>{module.eyebrow}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
          <h2 style={{ margin: 0, fontSize: 19, fontWeight: 600 }}>{module.title}</h2>
          {module.tag && <span style={{ fontSize: 11.5, color: 'var(--lt-fg-3)', fontFamily: 'var(--lt-font-mono)' }}>{module.tag}</span>}
        </div>
        <div style={{ marginTop: 5, fontSize: 12, color: 'var(--lt-fg-3)', lineHeight: 1.45 }}>{module.description}</div>
      </div>
      <div style={{ background: 'var(--lt-bg-2)', padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <DataCard />
        {module.fields.map((f) => <FieldRenderer key={f.key} field={f} />)}
      </div>
    </section>
  )
}

// ── Statistik-Akkordeon (eingeklappt) ───────────────────────────────────────

function StatCard({ label, value, sub, mono }: { label: string; value: string; sub?: string; mono?: boolean }) {
  return (
    <div style={{
      padding: '10px 12px', background: 'var(--lt-bg-1)',
      border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-md)',
    }}>
      <div className="lt-eyebrow" style={{ fontSize: 9.5 }}>{label}</div>
      <div style={{ fontSize: 17, fontWeight: 600, marginTop: 2, fontFamily: mono ? 'var(--lt-font-mono)' : 'inherit' }}>{value}</div>
      {sub && <div style={{ fontSize: 10.5, color: 'var(--lt-fg-3)', fontFamily: 'var(--lt-font-mono)', marginTop: 1 }}>{sub}</div>}
    </div>
  )
}

function BarBlock({ title, data, color }: { title: string; data: SparkDatum[]; color: string }) {
  if (data.length === 0) return null
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="lt-eyebrow" style={{ fontSize: 9.5, marginBottom: 6 }}>{title}</div>
      <Sparkbars data={data} width={300} height={30} gap={3} color={color} interactive />
    </div>
  )
}

function MobileStats({ summary, children }: { summary: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ background: 'var(--lt-bg-0)', borderBottom: '1px solid var(--lt-line-1)' }}>
      <button onClick={() => setOpen(!open)} style={{
        width: '100%', minHeight: 46, display: 'flex', alignItems: 'center', gap: 10,
        padding: '0 16px', background: 'transparent', border: 'none',
        color: 'var(--lt-fg-1)', cursor: 'pointer', textAlign: 'left',
      }}>
        <Icon name="chart" size={15} style={{ color: 'var(--lt-fg-3)' }} />
        <span style={{ fontSize: 13.5, fontWeight: 600 }}>Statistik</span>
        <span style={{ fontSize: 11.5, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)' }}>{summary}</span>
        <span style={{ flex: 1 }} />
        <Icon name={open ? 'chevDown' : 'chevron'} size={12} style={{ color: 'var(--lt-fg-3)' }} />
      </button>
      {open && <div style={{ padding: '2px 12px 14px' }}>{children}</div>}
    </div>
  )
}

// ── Ergebnis-Karte (generisch aus den Modul-Spalten) ────────────────────────

function ResultCard({ row, columns }: { row: Record<string, unknown>; columns: Column[] }) {
  const has = (k: string) => columns.some((c) => c.key === k)
  const diffCol = columns.find((c) => c.diffWith)
  const special = new Set(['filename', 'subdir', 'line', 'quelle', 'tag', diffCol?.key, diffCol?.diffWith])
  const rest = columns.filter((c) => !special.has(c.key))
  const chip: CSSProperties = {
    fontSize: 10.5, fontFamily: 'var(--lt-font-mono)', padding: '1px 6px',
    background: 'var(--lt-bg-2)', color: 'var(--lt-fg-2)', borderRadius: 3, flexShrink: 0,
  }
  return (
    <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--lt-line-1)', display: 'flex', flexDirection: 'column', gap: 7 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <Icon name="file" size={13} style={{ color: 'var(--lt-fg-4)' }} />
        <span style={{
          fontFamily: 'var(--lt-font-mono)', fontSize: 12.5, fontWeight: 500,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{str(row.filename)}</span>
        {has('line') && str(row.line) && (
          <span style={{ color: 'var(--lt-fg-4)', fontSize: 11, fontFamily: 'var(--lt-font-mono)', flexShrink: 0 }}>· Z. {str(row.line)}</span>
        )}
        <span style={{ flex: 1 }} />
        {has('tag') && str(row.tag) && <span style={chip}>{str(row.tag)}</span>}
      </div>

      {diffCol && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--lt-font-mono)', fontSize: 13.5, flexWrap: 'wrap' }}>
          <span style={{ color: 'var(--lt-err)' }}>{str(row[diffCol.diffWith!])}</span>
          <Icon name="chevron" size={11} style={{ color: 'var(--lt-fg-4)' }} />
          <Diff a={str(row[diffCol.diffWith!])} b={str(row[diffCol.key])} />
        </div>
      )}

      {rest.map((c) => {
        const v = str(row[c.key])
        if (!v) return null
        return (
          <div key={c.key} style={{ display: 'flex', gap: 8, fontSize: 12, minWidth: 0 }}>
            <span className="lt-eyebrow" style={{ fontSize: 9.5, flexShrink: 0, paddingTop: 2 }}>{c.label}</span>
            <span style={{
              color: c.danger ? 'var(--lt-err)' : 'var(--lt-fg-2)',
              fontFamily: c.mono ? 'var(--lt-font-mono)' : 'inherit',
              fontStyle: c.italic ? 'italic' : undefined,
              overflowWrap: 'anywhere',
            }}>{v}</span>
          </div>
        )
      })}

      {(str(row.quelle) || str(row.subdir)) && (
        <div style={{ display: 'flex', gap: 8, fontSize: 10.5, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-4)' }}>
          {str(row.subdir) && str(row.subdir) !== '.' && <span>{str(row.subdir)}/</span>}
          <span style={{ flex: 1 }} />
          {str(row.quelle) && <span>{str(row.quelle)}</span>}
        </div>
      )}
    </div>
  )
}

// ── Ergebnisse (Kopf + Statistik + Kartenliste) ─────────────────────────────

function MobileResults() {
  const { module, result, running, error, directory, progress } = useWorkbench()
  const [query, setQuery] = useState('')
  const [filterOpen, setFilterOpen] = useState(false)
  const [shown, setShown] = useState(CARD_PAGE)

  const rows = result?.results ?? []
  const columns = module.columns
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) => columns.some((c) => str(r[c.key]).toLowerCase().includes(q)))
  }, [rows, query, columns])

  const hasTag = columns.some((c) => c.key === 'tag')
  const byTag = hasTag ? aggregate(rows, 'tag') : []
  const byVolume = aggregate(rows, 'quelle')

  const iconBtn: CSSProperties = {
    width: 36, height: 36, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
    borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-2)', cursor: 'pointer', flexShrink: 0,
  }

  const download = () => {
    const blob = new Blob([toCsv(filtered, columns)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${module.id}_results.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section style={{ background: 'var(--lt-bg-0)' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '0 16px', height: 46,
        borderTop: '1px solid var(--lt-line-1)', borderBottom: '1px solid var(--lt-line-1)', background: 'var(--lt-bg-0)',
      }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Ergebnisse</h3>
        <span style={{ fontFamily: 'var(--lt-font-mono)', fontSize: 12.5 }}>
          <b>{filtered.length}</b> <span style={{ color: 'var(--lt-fg-3)' }}>Treffer</span>
        </span>
        <span style={{ flex: 1 }} />
        <button style={{ ...iconBtn, color: filterOpen ? 'var(--lt-primary)' : 'var(--lt-fg-2)' }}
          title="Treffer filtern" onClick={() => setFilterOpen((v) => !v)}>
          <Icon name="filter" size={14} />
        </button>
        <button style={{ ...iconBtn, opacity: filtered.length === 0 ? 0.5 : 1 }} title="CSV herunterladen"
          disabled={filtered.length === 0} onClick={download}>
          <Icon name="download" size={14} />
        </button>
      </div>

      {filterOpen && (
        <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--lt-line-1)' }}>
          <input value={query} onChange={(e) => { setQuery(e.target.value); setShown(CARD_PAGE) }}
            placeholder="Treffer filtern…" style={{
              width: '100%', boxSizing: 'border-box', padding: '8px 10px', fontSize: 13,
              background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
              borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', outline: 'none',
            }} />
        </div>
      )}

      {result && (
        <MobileStats summary={`${result.result_count} Treffer · ${(result.duration_ms / 1000).toFixed(2)} s`}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
            <StatCard label="Treffer" value={String(result.result_count)} sub={`aus ${result.files_checked} Dateien`} mono />
            <StatCard label="Dauer" value={`${(result.duration_ms / 1000).toFixed(2)} s`} mono />
            {hasTag && byTag[0] && <StatCard label="Tags" value={String(byTag.length)} sub={`${byTag[0].name} · ${byTag[0].count}`} mono />}
            {byVolume[0] && <StatCard label="Quellen" value={String(byVolume.length)} sub={`${byVolume[0].name} · ${byVolume[0].count}`} />}
          </div>
          {hasTag && <BarBlock title="Nach Tag" data={byTag} color="var(--lt-info)" />}
          <BarBlock title="Nach Quelle" data={byVolume} color="var(--lt-warn)" />
        </MobileStats>
      )}

      <div>
        {error ? (
          <div style={{ padding: '24px 16px', color: 'var(--lt-err)', fontSize: 13 }}>{error}</div>
        ) : running ? (
          <div style={{ padding: '30px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>
            {progress ? (
              <div style={{ maxWidth: 280, margin: '0 auto' }}>
                <div style={{ marginBottom: 8 }}>
                  {PHASE_LABELS[progress.phase] ?? progress.phase}… ({progress.done} von {progress.total || '?'})
                </div>
                <HBar value={progress.done} max={Math.max(progress.total, 1)} height={6} />
              </div>
            ) : 'Prüfung läuft…'}
          </div>
        ) : !result ? (
          <div style={{ padding: '30px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>
            {directory ? 'Bereit. „Prüfen" startet die Analyse.' : 'Datenverzeichnis angeben und „Prüfen".'}
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '30px 16px', textAlign: 'center', color: 'var(--lt-fg-3)', fontSize: 13 }}>Keine Treffer.</div>
        ) : (
          <>
            {filtered.slice(0, shown).map((r, i) => <ResultCard key={i} row={r} columns={columns} />)}
            {filtered.length > shown && (
              <button onClick={() => setShown(shown + CARD_PAGE)} style={{
                width: '100%', minHeight: 46, background: 'var(--lt-bg-1)', border: 'none',
                borderBottom: '1px solid var(--lt-line-1)', color: 'var(--lt-primary)',
                fontSize: 13, fontWeight: 600, cursor: 'pointer',
              }}>
                Mehr anzeigen ({filtered.length - shown} weitere)
              </button>
            )}
          </>
        )}
      </div>
    </section>
  )
}

// ── Gestapelte Workbench ────────────────────────────────────────────────────

export function MobileWorkbench() {
  const { module, activeId, run, running, directory, fileCount, result } = useWorkbench()
  const structure = useStructure()
  const [menuOpen, setMenuOpen] = useState(false)
  const [order, setOrder] = useState<Order>('params')

  const isApi = activeId === 'api'
  const isAdmin = activeId === 'admin'
  const isStructure = activeId === 'structure'
  const isIntro = activeId === 'intro'
  const isArtikelsuche = activeId === 'artikelsuche'
  const title = isApi ? 'API' : isAdmin ? 'Admin-Bereich' : isStructure ? 'Strukturanalyse' : isIntro ? 'Einführung' : isArtikelsuche ? 'Artikelsuche' : module.title
  const files = result ? String(result.files_checked) : fileCount != null ? String(fileCount) : '–'

  const panes = order === 'params'
    ? [<MobileParams key="p" />, <MobileResults key="r" />]
    : [<MobileResults key="r" />, <MobileParams key="p" />]

  return (
    <div style={{
      width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
      background: 'var(--lt-bg-1)', color: 'var(--lt-fg-1)', overflow: 'hidden', position: 'relative',
    }}>
      <header style={{
        height: 52, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10,
        padding: '0 8px 0 6px', background: 'var(--lt-bg-0)', borderBottom: '1px solid var(--lt-line-1)',
      }}>
        <button onClick={() => setMenuOpen(true)} aria-label="Menü öffnen" style={{
          width: 44, height: 44, flexShrink: 0, display: 'inline-flex', alignItems: 'center',
          justifyContent: 'center', background: 'transparent', border: 'none',
          color: 'var(--lt-fg-1)', cursor: 'pointer',
        }}>
          <Icon name="menu" size={20} />
        </button>
        <Logo size={17} />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flex: 1, minWidth: 0, overflow: 'hidden' }}>
          <span style={{ fontSize: 14, color: 'var(--lt-fg-3)', whiteSpace: 'nowrap' }}>Tools</span>
          <span style={{ color: 'var(--lt-fg-4)', fontSize: 13 }}>/</span>
          <span style={{
            fontSize: 14, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>{title}</span>
        </div>
        {isStructure ? (
          <button onClick={() => void structure.analyze()} disabled={structure.loading} style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, height: 36, padding: '0 14px',
            marginRight: 4, background: 'var(--lt-primary)', color: 'var(--lt-on-primary)',
            border: 'none', borderRadius: 'var(--lt-r-md)', fontSize: 13, fontWeight: 600,
            cursor: 'pointer', opacity: structure.loading ? 0.7 : 1, flexShrink: 0,
          }}>
            <Icon name="play" size={12} /> {structure.loading ? 'Analysiert…' : 'Analysieren'}
          </button>
        ) : !isApi && !isAdmin && !isIntro && !isArtikelsuche && (
          <button onClick={run} disabled={running} style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, height: 36, padding: '0 14px',
            marginRight: 4, background: 'var(--lt-primary)', color: 'var(--lt-on-primary)',
            border: 'none', borderRadius: 'var(--lt-r-md)', fontSize: 13, fontWeight: 600,
            cursor: 'pointer', opacity: running ? 0.7 : 1, flexShrink: 0,
          }}>
            <Icon name="play" size={12} /> {running ? 'Prüft…' : 'Prüfen'}
          </button>
        )}
      </header>

      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch' }}>
        {isApi ? (
          <>
            <div style={{ background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
              <ApiInfoConfig />
            </div>
            <ApiInfoMain />
          </>
        ) : isAdmin ? (
          <>
            <div style={{ background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
              <AdminConfig />
            </div>
            <AdminMain />
          </>
        ) : isStructure ? (
          <>
            <div style={{ background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
              <StructureConfig />
            </div>
            <StructureMain />
          </>
        ) : isIntro ? (
          <>
            <div style={{ background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
              <IntroConfig />
            </div>
            <IntroMain />
          </>
        ) : isArtikelsuche ? (
          <>
            <div style={{ background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
              <ArtikelsucheConfig />
            </div>
            <ArtikelsucheMain />
          </>
        ) : panes}
      </div>

      <footer style={{
        flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8, height: 34, padding: '0 16px',
        background: 'var(--lt-bg-0)', borderTop: '1px solid var(--lt-line-1)',
        fontSize: 11, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)',
        overflow: 'hidden', whiteSpace: 'nowrap',
      }}>
        <span style={{ width: 6, height: 6, borderRadius: 3, flexShrink: 0, background: directory ? 'var(--lt-primary)' : 'var(--lt-warn)' }} />
        <span style={{ color: 'var(--lt-fg-4)' }}>Daten:</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{directory || 'nicht gesetzt'}</span>
        <span style={{ flex: 1 }} />
        <span style={{ color: 'var(--lt-fg-4)' }}>Dateien:</span>
        <span>{files}</span>
      </footer>

      <MobileMenu open={menuOpen} onClose={() => setMenuOpen(false)} order={order} setOrder={setOrder} />
    </div>
  )
}
