import { useState, type CSSProperties } from 'react'
import { Icon } from '../design/icons'
import { kc, Segmented } from '../design/widgets'
import { loadAttrs, loadTags, type Field, type TagAttrPair } from '../modules/registry'
import { useWorkbench, type LayoutMode } from '../state/workbench'

const inputStyle: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '6px 9px', fontSize: 12,
  background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', outline: 'none',
}
const labelStyle: CSSProperties = { fontSize: 11, fontWeight: 600, color: 'var(--lt-fg-2)', marginBottom: 5, display: 'block' }
const card: CSSProperties = {
  background: 'var(--lt-bg-0)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-md)', boxShadow: 'var(--lt-shadow-1)', padding: 12,
}
const btnPrimary: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  background: 'var(--lt-primary)', color: 'var(--lt-on-primary)', border: '1px solid var(--lt-primary)',
  height: 36, padding: '0 16px', borderRadius: 'var(--lt-r-md)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
}

function TagsField({ field }: { field: Field }) {
  const { config, setField, directory } = useWorkbench()
  const value = (config[field.key] as string[]) ?? []
  const [loading, setLoading] = useState(false)
  const [draft, setDraft] = useState('')
  const [err, setErr] = useState('')

  const load = async () => {
    if (!directory.trim()) { setErr('Erst Datenpfad angeben.'); return }
    setLoading(true); setErr('')
    try { setField(field.key, await loadTags(field.loadTagsPath!, directory)) }
    catch (e) { setErr(String(e)) }
    finally { setLoading(false) }
  }
  const remove = (t: string) => setField(field.key, value.filter((x) => x !== t))
  const add = () => {
    const t = draft.trim()
    if (t && !value.includes(t)) setField(field.key, [...value, t])
    setDraft('')
  }

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>{field.label}</span>
        <span style={{ fontSize: 10, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)', background: 'var(--lt-bg-2)', padding: '1px 6px', borderRadius: 3 }}>{value.length}</span>
        <button onClick={load} disabled={loading} style={{
          fontSize: 11, padding: '3px 8px', background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
          borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-2)', cursor: 'pointer',
        }}>{loading ? 'lädt…' : 'Tags laden'}</button>
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder="Tag hinzufügen…" style={{ ...inputStyle, fontFamily: 'var(--lt-font-mono)' }} />
      </div>
      {err && <div style={{ fontSize: 11, color: 'var(--lt-err)', marginBottom: 6 }}>{err}</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {value.map((t) => (
          <span key={t} style={{
            display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 4px 2px 7px',
            background: 'var(--lt-primary-soft)', color: 'var(--lt-g-700)', border: '1px solid var(--lt-primary-line)',
            borderRadius: 3, fontSize: 11, fontFamily: 'var(--lt-font-mono)',
          }}>
            {t}
            <Icon name="x" size={8} style={{ opacity: 0.5, cursor: 'pointer' }} onClick={() => remove(t)} />
          </span>
        ))}
        {value.length === 0 && <span style={{ fontSize: 11, color: 'var(--lt-fg-4)' }}>Keine Tags gewählt.</span>}
      </div>
    </div>
  )
}

function PairsField({ field }: { field: Field }) {
  const { config, setField, directory } = useWorkbench()
  const value = (config[field.key] as TagAttrPair[]) ?? []
  const [tagOptions, setTagOptions] = useState<string[]>([])
  const [attrOptions, setAttrOptions] = useState<Record<string, string[]>>({})
  const [loadingTags, setLoadingTags] = useState(false)
  const [err, setErr] = useState('')

  const loadTagOptions = async () => {
    if (!directory.trim() || !field.loadTagsPath) { setErr('Erst Datenpfad angeben.'); return }
    setLoadingTags(true); setErr('')
    try { setTagOptions(await loadTags(field.loadTagsPath, directory)) }
    catch (e) { setErr(String(e)) }
    finally { setLoadingTags(false) }
  }

  const ensureAttrOptions = async (tag: string) => {
    if (!directory.trim() || !field.loadAttrsPath || !tag || attrOptions[tag]) return
    try {
      const attrs = await loadAttrs(field.loadAttrsPath, directory, tag)
      setAttrOptions((prev) => ({ ...prev, [tag]: attrs }))
    } catch { /* Vorschläge sind optional — Freitext bleibt möglich */ }
  }

  const updateRow = (i: number, patch: Partial<TagAttrPair>) =>
    setField(field.key, value.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  const addRow = () => setField(field.key, [...value, { tag: '', attribute: '' }])
  const removeRow = (i: number) => setField(field.key, value.filter((_, idx) => idx !== i))

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>{field.label}</span>
        {field.loadTagsPath && (
          <button onClick={loadTagOptions} disabled={loadingTags} style={{
            fontSize: 11, padding: '3px 8px', background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
            borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-2)', cursor: 'pointer',
          }}>{loadingTags ? 'lädt…' : 'Tags laden'}</button>
        )}
      </div>
      {err && <div style={{ fontSize: 11, color: 'var(--lt-err)', marginBottom: 6 }}>{err}</div>}
      <datalist id={`${field.key}-tags`}>
        {tagOptions.map((t) => <option key={t} value={t} />)}
      </datalist>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {value.map((row, i) => (
          <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input value={row.tag} list={`${field.key}-tags`} placeholder="Tag (leer = alle)"
              onChange={(e) => updateRow(i, { tag: e.target.value })}
              style={{ ...inputStyle, flex: 1, fontFamily: 'var(--lt-font-mono)' }} />
            <input value={row.attribute} list={`${field.key}-attrs-${row.tag}`} placeholder="Attribut"
              onFocus={() => ensureAttrOptions(row.tag)}
              onChange={(e) => updateRow(i, { attribute: e.target.value })}
              style={{ ...inputStyle, flex: 1, fontFamily: 'var(--lt-font-mono)' }} />
            <datalist id={`${field.key}-attrs-${row.tag}`}>
              {(attrOptions[row.tag] ?? []).map((a) => <option key={a} value={a} />)}
            </datalist>
            <Icon name="x" size={12} style={{ opacity: 0.5, cursor: 'pointer', flexShrink: 0 }} onClick={() => removeRow(i)} />
          </div>
        ))}
        {value.length === 0 && <span style={{ fontSize: 11, color: 'var(--lt-fg-4)' }}>Keine Quellen gewählt.</span>}
      </div>
      <button onClick={addRow} style={{
        display: 'inline-flex', alignItems: 'center', gap: 5, marginTop: 8,
        fontSize: 11, padding: '3px 8px', background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
        borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-2)', cursor: 'pointer',
      }}><Icon name="plus" size={10} /> Quelle hinzufügen</button>
    </div>
  )
}

export function FieldRenderer({ field }: { field: Field }) {
  const { config, setField } = useWorkbench()
  if (field.type === 'tags') return <TagsField field={field} />
  if (field.type === 'pairs') return <PairsField field={field} />

  if (field.type === 'select') {
    const value = config[field.key] as string
    // Bei wenigen kurzen Optionen ein Segmented, sonst native Select.
    const compact = field.options!.every((o) => o.length <= 12) && field.options!.length <= 3
    return (
      <div>
        <label style={labelStyle}>{field.label}</label>
        {compact ? (
          <Segmented options={field.options!} value={value} onChange={(v) => setField(field.key, v)} />
        ) : (
          <select value={value} onChange={(e) => setField(field.key, e.target.value)} style={inputStyle}>
            {field.options!.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        )}
      </div>
    )
  }

  if (field.type === 'checkbox') {
    const value = config[field.key] as boolean
    return (
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
        <input type="checkbox" checked={value} onChange={(e) => setField(field.key, e.target.checked)}
          style={{ accentColor: 'var(--lt-primary)' }} />
        <span style={{ fontSize: 12 }}>{field.label}</span>
      </label>
    )
  }

  // text
  const value = config[field.key] as string
  return (
    <div>
      <label style={labelStyle}>{field.label}</label>
      <input value={value} placeholder={field.placeholder}
        onChange={(e) => setField(field.key, e.target.value)}
        style={{ ...inputStyle, fontFamily: field.mono ? 'var(--lt-font-mono)' : 'inherit' }} />
    </div>
  )
}

export function DataCard() {
  const { directory, fileCount, setDataDialogOpen } = useWorkbench()
  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: directory ? 8 : 0 }}>
        <Icon name="folder" size={13} style={{ color: directory ? 'var(--lt-primary)' : 'var(--lt-fg-4)' }} />
        <span style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>Daten</span>
        {fileCount != null && <span style={{ fontSize: 10, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)', background: 'var(--lt-bg-2)', padding: '1px 6px', borderRadius: 3 }}>{fileCount} XML</span>}
        <button onClick={() => setDataDialogOpen(true)} style={{
          fontSize: 11, padding: '3px 8px', background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
          borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-2)', cursor: 'pointer',
        }}>Daten wählen…</button>
      </div>
      {directory
        ? <div style={{ fontSize: 10.5, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)', wordBreak: 'break-all' }}>{directory}</div>
        : null}
    </div>
  )
}

export function ConfigPane({ layout }: { layout: LayoutMode }) {
  const { module, run, running } = useWorkbench()
  return (
    <section style={{
      gridArea: 'cfg', background: 'var(--lt-bg-0)',
      borderRight: layout === 'left' ? '1px solid var(--lt-line-1)' : 'none',
      borderLeft: layout === 'right' ? '1px solid var(--lt-line-1)' : 'none',
      borderBottom: layout === 'bottom' ? '1px solid var(--lt-line-1)' : 'none',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ padding: '14px 18px 12px', background: 'var(--lt-bg-2)', borderBottom: '1px solid var(--lt-line-1)' }}>
        <div className="lt-eyebrow" style={{ marginBottom: 4 }}>{module.eyebrow}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{module.title}</h2>
          {module.tag && <span style={{ fontSize: 11, color: 'var(--lt-fg-3)', fontFamily: 'var(--lt-font-mono)' }}>{module.tag}</span>}
        </div>
        <p style={{ margin: '6px 0 0', color: 'var(--lt-fg-3)', fontSize: 12, lineHeight: 1.45 }}>{module.description}</p>
      </div>

      <div className="cfg-scroll" style={{
        overflowY: 'auto', flex: 1, background: 'var(--lt-bg-2)', padding: 12,
        display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        <DataCard />
        {module.fields.map((f) => <FieldRenderer key={f.key} field={f} />)}
      </div>

      <div style={{
        height: 48, boxSizing: 'border-box', padding: '0 14px', borderTop: '1px solid var(--lt-line-1)',
        background: 'var(--lt-bg-2)', display: 'flex', gap: 10, alignItems: 'center',
      }}>
        <button onClick={run} disabled={running} style={{ ...btnPrimary, flex: 1, opacity: running ? 0.7 : 1 }}>
          <Icon name="play" size={12} />
          {running ? 'Prüfe…' : 'Prüfen'}
          <span style={{ opacity: 0.65, fontSize: 11, marginLeft: 4, fontFamily: 'var(--lt-font-mono)' }}>{kc('↵')}</span>
        </button>
      </div>
    </section>
  )
}
