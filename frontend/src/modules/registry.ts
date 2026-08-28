// Modul-Registry: eine deklarative Beschreibung jeder Prüfung steuert
// Navigation, Konfigurator-Pane und Ergebnis-Tabelle generisch.
import { api, pollJob, type CheckResult, type ValidatorResponse } from '../api/client'

export type FieldType = 'text' | 'select' | 'checkbox' | 'tags' | 'pairs' | 'wordlist'

export interface TagAttrPair { tag: string; attribute: string }
export interface SpellingPair { alt: string; neu: string }

export interface Field {
  type: FieldType
  key: string
  label: string
  placeholder?: string
  mono?: boolean
  options?: string[]
  /** Endpunkt, der Tag-Vorschläge liefert (für type: 'tags' | 'pairs'). */
  loadTagsPath?: string
  /** Endpunkt, der Attribut-Vorschläge für ein Tag liefert (für type: 'pairs'). */
  loadAttrsPath?: string
  default: string | boolean | string[] | TagAttrPair[] | SpellingPair[]
}

export interface Column {
  key: string
  label: string
  width?: number
  align?: 'right'
  mono?: boolean
  danger?: boolean
  italic?: boolean
  chip?: boolean
  /** Spalte als Diff gegen das Feld <diffWith> rendern. */
  diffWith?: string
}

export interface JobProgress { phase: string; done: number; total: number }

export interface ModuleDef {
  id: string
  label: string
  group: string
  eyebrow: string
  title: string
  tag?: string
  description: string
  fields: Field[]
  columns: Column[]
  /** Entweder `run` (einzelne Anfrage) oder `runJob` (Start + Poll, siehe unten) angeben. */
  run?: (directory: string, config: Config) => Promise<CheckResult>
  /** Job-basierte Ausführung (Start + Poll) statt einer einzelnen Anfrage —
   *  für Prüfungen, die zu lange dauern für `run`. Hat Vorrang vor `run`,
   *  wenn gesetzt (siehe `workbench.tsx`). */
  runJob?: (directory: string, config: Config, onProgress: (p: JobProgress) => void) => Promise<CheckResult>
}

export type Config = Record<string, string | boolean | string[] | TagAttrPair[] | SpellingPair[]>

const COMMON_TAIL: Column[] = [
  { key: 'quelle', label: 'Gedruckte Ausgabe', width: 150, mono: true },
]
const HEAD: Column[] = [
  { key: 'filename', label: 'Datei', mono: true },
  { key: 'subdir', label: 'Verz.', width: 90 },
  { key: 'line', label: 'Zeile', width: 72, align: 'right', mono: true },
]

export const MODULES: ModuleDef[] = [
  {
    id: 'validator', label: 'XML/TL0 Validator', group: 'XML',
    eyebrow: 'XML', title: 'Validator', tag: 'Wohlgeformtheit · TL0',
    description: 'Prüft XML-Dateien auf Wohlgeformtheit oder gegen das TEI-Lex 0 Schema.',
    fields: [
      { type: 'select', key: 'validation_type', label: 'Validierungstyp', default: 'Wohlgeformtheit (Well-formed XML)',
        options: ['Wohlgeformtheit (Well-formed XML)', 'TEI-Lex 0 Schema (RelaxNG)'] },
    ],
    columns: [...HEAD, { key: 'column', label: 'Spalte', width: 72, align: 'right', mono: true },
      { key: 'error', label: 'Fehler', danger: true }, ...COMMON_TAIL],
    run: async (directory, c) => {
      const r = await api.post<ValidatorResponse>('/checks/validator', { directory, validation_type: c.validation_type })
      const wf = c.validation_type === 'TEI-Lex 0 Schema (RelaxNG)'
      const results = wf ? r.schema_errors : r.wellformed
      return { results, files_checked: r.files_checked, result_count: results.length, duration_ms: r.duration_ms }
    },
  },
  {
    id: 'pathfinder', label: 'Tag- und Pfadsuche', group: 'XML',
    eyebrow: 'XML', title: 'Tag- und Pfadsuche',
    description: 'Suche nach Tags oder Pfaden, inkl. Wildcards. Beispiele: bedeutung · sense/sense · sense/*/bibl',
    fields: [
      { type: 'text', key: 'user_input', label: 'Tag oder Pfad', placeholder: 'z. B. bedeutung oder sense/*/bibl', mono: true, default: '' },
    ],
    columns: [...HEAD, { key: 'full_path', label: 'XPath', mono: true },
      { key: 'text_content', label: 'Inhalt' }, ...COMMON_TAIL],
    run: (directory, c) => api.post<CheckResult>('/checks/pathfinder', { directory, user_input: c.user_input }),
  },
  {
    id: 'unique', label: 'Einmaligkeit', group: 'XML',
    eyebrow: 'XML', title: 'Einmaligkeit',
    description: 'Prüft, ob Tags, Inhalte oder Attribute innerhalb eines Dokuments einmalig sind.',
    fields: [
      { type: 'select', key: 'mode', label: 'Prüfmodus', default: 'Tag',
        options: ['Tag', 'Tag-Inhalt', 'Tag & Attribut', 'Attribut'] },
      { type: 'text', key: 'tag_name', label: 'Tag-Name', placeholder: 'z. B. lemma', default: '' },
      { type: 'text', key: 'attribute_name', label: 'Attribut-Name', placeholder: 'z. B. xml:id', default: '' },
    ],
    columns: [...HEAD, { key: 'error_type', label: 'Fehlertyp' }, { key: 'details', label: 'Details' }, ...COMMON_TAIL],
    run: (directory, c) => api.post<CheckResult>('/checks/uniqueness',
      { directory, mode: c.mode, tag_name: c.tag_name, attribute_name: c.attribute_name }),
  },
  {
    id: 'nesting', label: 'Verschachtelung', group: 'XML',
    eyebrow: 'XML', title: 'Verschachtelung',
    description: 'Analysiert Verschachtelungstiefe eines Tags oder sucht Pfad-Muster im Baum.',
    fields: [
      { type: 'select', key: 'search_mode', label: 'Modus', default: 'Direkte Verschachtelung',
        options: ['Direkte Verschachtelung', 'Beliebige Verschachtelung', 'Pfad / Wildcard'] },
      { type: 'text', key: 'tag_input', label: 'Tag-Name', placeholder: 'z. B. sense', default: '' },
      { type: 'text', key: 'path_input', label: 'Pfad-Muster', placeholder: 'z. B. sense/*/form', mono: true, default: '' },
    ],
    columns: [...HEAD, { key: 'depth', label: 'Tiefe', width: 72, align: 'right' },
      { key: 'details', label: 'Pfad', mono: true }, ...COMMON_TAIL],
    run: (directory, c) => api.post<CheckResult>('/checks/nesting',
      { directory, search_mode: c.search_mode, tag_input: c.tag_input, path_input: c.path_input }),
  },
  {
    id: 'content', label: 'Inhalt / Leere Tags', group: 'XML',
    eyebrow: 'XML', title: 'Inhalt / Leere Tags',
    description: 'Durchsucht Tags nach Textinhalten oder findet nicht-leere Tags.',
    fields: [
      { type: 'tags', key: 'tags_to_search', label: 'Tags', loadTagsPath: '/checks/tag-content/tags', default: [] },
      { type: 'text', key: 'search_text', label: 'Suchtext (optional)', placeholder: 'leer = alle nicht-leeren', default: '' },
      { type: 'checkbox', key: 'include_whitespace', label: 'Leerzeichen/Umbrüche berücksichtigen', default: true },
    ],
    columns: [...HEAD, { key: 'tag', label: 'Tag', width: 130, chip: true },
      { key: 'attribute', label: 'Attribut', width: 110 }, { key: 'text', label: 'Inhalt' }, ...COMMON_TAIL],
    run: (directory, c) => api.post<CheckResult>('/checks/tag-content/search', {
      directory, tags_to_search: c.tags_to_search, search_text: c.search_text,
      include_whitespace: c.include_whitespace, attrs_to_filter: [], attr_value: '',
      is_single_tag_mode: (c.tags_to_search as string[]).length === 1,
    }),
  },
  {
    id: 'references', label: 'Verweise', group: 'XML',
    eyebrow: 'XML', title: 'Verweise',
    description: 'Prüft Verweise (BDO-Artikelreferenzen gegen die Datenbank und/oder http(s)-Links) auf Erreichbarkeit ihres Ziels.',
    fields: [
      { type: 'pairs', key: 'sources', label: 'Verweisquellen (Tag + Attribut)',
        loadTagsPath: '/checks/tag-content/tags', loadAttrsPath: '/checks/tag-content/attrs',
        default: [{ tag: 'verweis', attribute: 'ziel' }] },
      { type: 'checkbox', key: 'check_http_links', label: 'Zusätzlich alle http(s)-Links prüfen (Attribute und Text)', default: false },
      { type: 'checkbox', key: 'include_fehlt_marked', label: 'Bereits als fehlend markierte Verweise (@fehlt="ja") mitprüfen', default: true },
    ],
    columns: [...HEAD, { key: 'tag', label: 'Tag', width: 110, chip: true },
      { key: 'attribute', label: 'Attribut', width: 110 },
      { key: 'kind', label: 'Art', width: 80, chip: true },
      { key: 'target', label: 'Ziel', mono: true },
      { key: 'status', label: 'Status', danger: true },
      { key: 'fehlt_marked', label: 'bereits markiert', width: 130 },
      ...COMMON_TAIL],
    runJob: async (directory, c, onProgress) => {
      const sources = (c.sources as TagAttrPair[]) ?? []
      const start = await api.post<{ job_id: string; total: number }>('/checks/references/run', {
        directory, sources,
        check_http_links: c.check_http_links, include_fehlt_marked: c.include_fehlt_marked,
      })
      const r = await pollJob<CheckResult>(`/checks/references/run/${start.job_id}`, onProgress)
      const results = r.results.map((row) => ({
        ...row,
        kind: row.kind === 'link' ? 'Link' : 'Artikel',
        fehlt_marked: row.fehlt_marked ? 'ja' : '',
      }))
      return { ...r, results }
    },
  },
  {
    id: 'stats', label: 'Anzahl und Länge', group: 'Stil und Schreibung',
    eyebrow: 'Stil und Schreibung', title: 'Anzahl und Länge',
    description: 'Wertet pro Datei Anzahl und Textlänge (min/max/Ø) eines Tags aus.',
    fields: [
      { type: 'text', key: 'tag_name', label: 'Tag-Name', placeholder: 'z. B. sense', default: 'sense' },
    ],
    columns: [
      { key: 'filename', label: 'Datei', mono: true }, { key: 'subdir', label: 'Verz.', width: 90 },
      { key: 'count', label: 'Anzahl', width: 80, align: 'right', mono: true },
      { key: 'min_length', label: 'Min', width: 70, align: 'right', mono: true },
      { key: 'max_length', label: 'Max', width: 70, align: 'right', mono: true },
      { key: 'avg_length', label: 'Ø', width: 70, align: 'right', mono: true }, ...COMMON_TAIL,
    ],
    run: (directory, c) => api.post<CheckResult>('/checks/senses-stats', { directory, tag_name: c.tag_name }),
  },
  {
    id: 'spelling', label: 'Alte Rechtschreibung', group: 'Stil und Schreibung',
    eyebrow: 'Stil und Schreibung', title: 'Rechtschreibung', tag: 'vor 1996/2006',
    description: 'Sucht hochdeutsche Reformschreibungen in Definitionen, Etymologie, Literatur.',
    fields: [
      { type: 'tags', key: 'included_tags', label: 'Tags', loadTagsPath: '/checks/spelling/tags', default: [] },
      { type: 'wordlist', key: 'custom_spellings', label: 'Wortliste', default: [] },
      { type: 'select', key: 'custom_list_mode', label: 'Wortlisten-Modus', default: 'Ergänzen', options: ['Ergänzen', 'Ersetzen'] },
    ],
    columns: [...HEAD, { key: 'tag', label: 'Tag', width: 120, chip: true },
      { key: 'gefunden', label: 'Gefunden', width: 122, mono: true, danger: true },
      { key: 'vorschlag', label: 'Vorschlag', width: 150, diffWith: 'gefunden' },
      { key: 'kontext', label: 'Kontext', italic: true }, ...COMMON_TAIL],
    run: (directory, c) => api.post<CheckResult>('/checks/spelling/search', {
      directory, included_tags: c.included_tags, custom_spellings: c.custom_spellings,
      custom_list_mode: c.custom_list_mode === 'Ersetzen' ? 'replace' : 'extend',
    }),
  },
]

export const MODULE_GROUPS = ['Start', 'XML', 'Stil und Schreibung', 'LLM'] as const

export function moduleById(id: string): ModuleDef | undefined {
  return MODULES.find((m) => m.id === id)
}

export function defaultConfig(m: ModuleDef): Config {
  const c: Config = {}
  for (const f of m.fields) {
    c[f.key] = Array.isArray(f.default) ? ([...f.default] as string[] | TagAttrPair[] | SpellingPair[]) : f.default
  }
  return c
}

/** Tag-Vorschläge für ein 'tags'-Feld laden.
 *  Liefert der Endpunkt default_excluded (Rechtschreibung), werden diese
 *  Tags nicht vorausgewählt — sie lassen sich manuell wieder hinzufügen. */
export async function loadTags(path: string, directory: string): Promise<string[]> {
  const r = await api.post<{ tags: string[]; default_excluded?: string[] }>(path, { directory })
  const excluded = new Set(r.default_excluded ?? [])
  return r.tags.filter((t) => !excluded.has(t))
}

/** Attribut-Vorschläge für ein Tag laden (für type: 'pairs', z. B. Verweisquellen). */
export async function loadAttrs(path: string, directory: string, tag: string): Promise<string[]> {
  const r = await api.post<{ attrs: string[] }>(path, { directory, tags_filter: tag ? [tag] : [] })
  return r.attrs
}
