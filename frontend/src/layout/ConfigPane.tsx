import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { api } from '../api/client'
import { Icon } from '../design/icons'
import { kc, Segmented } from '../design/widgets'
import { loadAttrs, loadTags, type Field, type SpellingPair, type TagAttrPair } from '../modules/registry'
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
const btnGhost: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  fontSize: 11, padding: '3px 8px', background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
  borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-2)', cursor: 'pointer',
}
const chipIncluded: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 4px 2px 7px',
  background: 'var(--lt-primary-soft)', color: 'var(--lt-g-700)', border: '1px solid var(--lt-primary-line)',
  borderRadius: 3, fontSize: 11, fontFamily: 'var(--lt-font-mono)',
}
const chipExcluded: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 7px',
  background: 'var(--lt-err-soft)', color: 'var(--lt-err)', border: '1px solid var(--lt-err-line)',
  borderRadius: 3, fontSize: 11, fontFamily: 'var(--lt-font-mono)', cursor: 'pointer',
}
const chipOption: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 7px',
  background: 'var(--lt-bg-1)', color: 'var(--lt-fg-2)', border: '1px solid var(--lt-line-1)',
  borderRadius: 3, fontSize: 11, fontFamily: 'var(--lt-font-mono)', cursor: 'pointer',
}
const chipOptionUsed: CSSProperties = { ...chipOption, opacity: 0.4, cursor: 'default' }

function TagsField({ field }: { field: Field }) {
  const { config, setField, directory } = useWorkbench()
  const value = (config[field.key] as string[]) ?? []
  const [excluded, setExcluded] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [draft, setDraft] = useState('')
  const [err, setErr] = useState('')
  const configFileRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    if (!directory.trim()) { setErr('Erst Datenpfad angeben.'); return }
    setLoading(true); setErr('')
    try {
      const r = await api.post<{ tags: string[]; default_excluded?: string[] }>(field.loadTagsPath!, { directory })
      const defaultExcluded = new Set(r.default_excluded ?? [])
      setField(field.key, r.tags.filter((t) => !defaultExcluded.has(t)))
      setExcluded(r.tags.filter((t) => defaultExcluded.has(t)))
    }
    catch (e) { setErr(String(e)) }
    finally { setLoading(false) }
  }
  const exclude = (t: string) => {
    setField(field.key, value.filter((x) => x !== t))
    setExcluded((e) => [...e, t].sort())
  }
  const include = (t: string) => {
    setExcluded((e) => e.filter((x) => x !== t))
    setField(field.key, [...value, t])
  }
  const add = () => {
    const t = draft.trim()
    if (t && !value.includes(t)) setField(field.key, [...value, t])
    setExcluded((e) => e.filter((x) => x !== t))
    setDraft('')
  }

  const downloadConfig = () => {
    const json = JSON.stringify({ included: value, excluded }, null, 2)
    const blob = new Blob([json], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${field.key}_konfiguration.json`; a.click()
    URL.revokeObjectURL(url)
  }
  const uploadConfig = async (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    setErr('')
    try {
      const data = JSON.parse(await file.text()) as { included?: string[]; excluded?: string[] }
      setField(field.key, data.included ?? [])
      setExcluded(data.excluded ?? [])
    } catch (e) { setErr(String(e)) }
    finally { if (configFileRef.current) configFileRef.current.value = '' }
  }

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>{field.label}</span>
        <span style={{ fontSize: 10, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)', background: 'var(--lt-bg-2)', padding: '1px 6px', borderRadius: 3 }}>{value.length}</span>
        <button onClick={load} disabled={loading} style={btnGhost}>{loading ? 'lädt…' : 'Tags laden'}</button>
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder="Tag hinzufügen…" style={{ ...inputStyle, fontFamily: 'var(--lt-font-mono)' }} />
      </div>
      {err && <div style={{ fontSize: 11, color: 'var(--lt-err)', marginBottom: 6 }}>{err}</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {value.map((t) => (
          <span key={t} style={chipIncluded}>
            {t}
            <Icon name="x" size={8} style={{ opacity: 0.5, cursor: 'pointer' }} onClick={() => exclude(t)} />
          </span>
        ))}
        {value.length === 0 && <span style={{ fontSize: 11, color: 'var(--lt-fg-4)' }}>Keine Tags gewählt.</span>}
      </div>
      {excluded.length > 0 && (
        <>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--lt-err)', margin: '10px 0 4px' }}>
            Ausgeschlossene Tags <span style={{ fontWeight: 400, opacity: 0.75 }}>— anklicken, um wieder einzuschließen</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {excluded.map((t) => (
              <span key={t} title="Wieder einschließen" style={chipExcluded} onClick={() => include(t)}>{t}</span>
            ))}
          </div>
        </>
      )}
      <div style={{ display: 'flex', gap: 6, marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--lt-line-1)' }}>
        <button onClick={downloadConfig} style={btnGhost}><Icon name="download" size={10} /> Konfiguration herunterladen</button>
        <button onClick={() => configFileRef.current?.click()} style={btnGhost}><Icon name="upload" size={10} /> Konfiguration hochladen</button>
        <input ref={configFileRef} type="file" accept=".json" style={{ display: 'none' }} onChange={(e) => uploadConfig(e.target.files)} />
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

  const usedTags = new Set(value.map((r) => r.tag).filter(Boolean))
  const addTagOption = (t: string) => {
    if (usedTags.has(t)) return
    const emptyIdx = value.findIndex((r) => !r.tag)
    if (emptyIdx >= 0) updateRow(emptyIdx, { tag: t })
    else setField(field.key, [...value, { tag: t, attribute: '' }])
  }

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>{field.label}</span>
        {tagOptions.length > 0 && (
          <span style={{ fontSize: 10, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-3)', background: 'var(--lt-bg-2)', padding: '1px 6px', borderRadius: 3 }}>{tagOptions.length}</span>
        )}
        {field.loadTagsPath && (
          <button onClick={loadTagOptions} disabled={loadingTags} style={btnGhost}>{loadingTags ? 'lädt…' : 'Tags laden'}</button>
        )}
      </div>
      {err && <div style={{ fontSize: 11, color: 'var(--lt-err)', marginBottom: 6 }}>{err}</div>}
      <datalist id={`${field.key}-tags`}>
        {tagOptions.map((t) => <option key={t} value={t} />)}
      </datalist>
      {tagOptions.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--lt-fg-2)', marginBottom: 4 }}>
            Verfügbare Tags <span style={{ fontWeight: 400, opacity: 0.75 }}>— anklicken, um als Quelle hinzuzufügen</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {tagOptions.map((t) => (
              <span key={t} title={usedTags.has(t) ? 'Bereits als Quelle gewählt' : 'Als Quelle hinzufügen'}
                style={usedTags.has(t) ? chipOptionUsed : chipOption} onClick={() => addTagOption(t)}>{t}</span>
            ))}
          </div>
        </div>
      )}
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

function parseSpellingCsv(text: string): SpellingPair[] {
  const pairs: SpellingPair[] = []
  for (const line of text.split(/\r?\n/)) {
    const raw = line.trim()
    if (!raw) continue
    const [alt, neu] = raw.split(';').map((s) => s.trim())
    if (!alt || !neu || alt.toLowerCase() === 'alt') continue
    pairs.push({ alt, neu })
  }
  return pairs
}

function WordlistField({ field }: { field: Field }) {
  const { config, setField } = useWorkbench()
  const custom = (config[field.key] as SpellingPair[]) ?? []
  const [builtin, setBuiltin] = useState<SpellingPair[]>([])
  const [builtinCount, setBuiltinCount] = useState<number | null>(null)
  const [showList, setShowList] = useState(false)
  const [query, setQuery] = useState('')
  const [err, setErr] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.get<{ builtin_count: number; spellings: SpellingPair[] }>('/checks/spelling/wordlist')
      .then((r) => { setBuiltinCount(r.builtin_count); setBuiltin(r.spellings) })
      .catch((e) => setErr(String(e)))
  }, [])

  const combined = useMemo(() => [...builtin, ...custom], [builtin, custom])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return combined
    return combined.filter((p) => p.alt.toLowerCase().includes(q) || p.neu.toLowerCase().includes(q))
  }, [combined, query])

  const download = () => {
    const csv = ['alt;neu', ...combined.map((p) => `${p.alt};${p.neu}`)].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'wortliste.csv'; a.click()
    URL.revokeObjectURL(url)
  }
  const upload = async (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    setErr('')
    try { setField(field.key, parseSpellingCsv(await file.text())) }
    catch (e) { setErr(String(e)) }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon name="book" size={13} style={{ color: 'var(--lt-primary)' }} />
        <span style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>{field.label}</span>
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--lt-fg-3)', marginBottom: 10, lineHeight: 1.5 }}>
        Integrierte Wortliste: <strong style={{ color: 'var(--lt-fg-1)' }}>{builtinCount ?? '…'}</strong> Einträge.
        {custom.length > 0 && <> Eigene Wortliste: <strong style={{ color: 'var(--lt-fg-1)' }}>{custom.length}</strong> Einträge.</>}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button onClick={() => setShowList((s) => !s)} style={btnGhost}>{showList ? 'Wortliste ausblenden' : 'Wortliste anzeigen'}</button>
        <button onClick={download} style={btnGhost}><Icon name="download" size={10} /> Wortliste herunterladen</button>
        <button onClick={() => fileRef.current?.click()} style={btnGhost}><Icon name="upload" size={10} /> Wortliste hochladen</button>
        {custom.length > 0 && <button onClick={() => setField(field.key, [])} style={btnGhost}>Eigene Wortliste entfernen</button>}
      </div>
      <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={(e) => upload(e.target.files)} />
      {err && <div style={{ fontSize: 11, color: 'var(--lt-err)', marginTop: 6 }}>{err}</div>}
      {showList && (
        <div style={{ marginTop: 10 }}>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filtern…"
            style={{ ...inputStyle, fontFamily: 'var(--lt-font-mono)', marginBottom: 6 }} />
          <div style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-sm)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '4px 8px', position: 'sticky', top: 0, background: 'var(--lt-bg-1)', borderBottom: '1px solid var(--lt-line-1)' }}>alt</th>
                  <th style={{ textAlign: 'left', padding: '4px 8px', position: 'sticky', top: 0, background: 'var(--lt-bg-1)', borderBottom: '1px solid var(--lt-line-1)' }}>neu</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p, i) => (
                  <tr key={i}>
                    <td style={{ padding: '3px 8px', fontFamily: 'var(--lt-font-mono)' }}>{p.alt}</td>
                    <td style={{ padding: '3px 8px', fontFamily: 'var(--lt-font-mono)' }}>{p.neu}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={2} style={{ padding: '8px', color: 'var(--lt-fg-4)' }}>Keine Treffer.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export function FieldRenderer({ field }: { field: Field }) {
  const { config, setField } = useWorkbench()
  if (field.type === 'tags') return <TagsField field={field} />
  if (field.type === 'pairs') return <PairsField field={field} />
  if (field.type === 'wordlist') return <WordlistField field={field} />

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
