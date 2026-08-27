// Baum-Browser für den "Datenbank"-Tab im Daten-Dialog: Wörterbuch > Buchstabe
// > Artikel, gegen den serverseitigen Index-Cache (wbdb/index_store.py).
// Flache Liste sichtbarer Zeilen mit `depth` statt verschachteltem Baum-Objekt
// (wie im v1-Vorbild), Buchstaben lazy nachgeladen beim Aufklappen.
//
// Auswahl-Semantik: drei Sets (Ressourcen/Buchstaben/Artikel). Eine volle
// Ressourcen-/Buchstaben-Auswahl wird beim Abwählen eines einzelnen Kindes in
// Geschwister aufgesplittet ("Ressource minus dieser Buchstabe" bzw.
// "Buchstabe minus dieser Artikel") statt komplett zu leeren — das
// Elternelement wird dazu bei Bedarf lazy nachgeladen.
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Icon } from '../design/icons'
import { dataApi, type DbArticleSummary, type DbResourceSummary, type DbSearchHit, type DbSelection } from '../api/client'

const SEP = '\u0000'
const letterKey = (resourceId: string, letter: string) => `${resourceId}${SEP}${letter}`
const articleKey = (resourceId: string, sourcePath: string) => `${resourceId}${SEP}${sourcePath}`
const splitKey = (key: string): [string, string] => {
  const i = key.indexOf(SEP)
  return [key.slice(0, i), key.slice(i + 1)]
}
const letterOfPath = (sourcePath: string) => sourcePath.split('/')[1] ?? ''

const row: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
  borderRadius: 'var(--lt-r-sm)', cursor: 'pointer', minWidth: 0,
}
const rowLabel: CSSProperties = { flex: 1, fontSize: 12.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
const rowCount: CSSProperties = { fontSize: 10, fontFamily: 'var(--lt-font-mono)', color: 'var(--lt-fg-4)', flexShrink: 0 }
const chevronBtn: CSSProperties = { width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, color: 'var(--lt-fg-4)' }

function Chevron({ expanded, onClick }: { expanded: boolean; onClick: () => void }) {
  // Der Chevron sitzt in einem <label>, das ein Checkbox-Kind hat: ein Klick
  // aktiviert nativ auch die Checkbox, unabhängig von stopPropagation() (das
  // verhindert nur das JS-Bubbling, nicht die Browser-eigene Label-Aktivierung).
  // Nur preventDefault() unterdrückt das.
  return (
    <span style={chevronBtn} onClick={(e) => { e.preventDefault(); e.stopPropagation(); onClick() }}>
      <Icon name={expanded ? 'chevDown' : 'chevron'} size={11} />
    </span>
  )
}

export function DbTree({ onSelectionChange }: { onSelectionChange: (selection: DbSelection, count: number) => void }) {
  const [tree, setTree] = useState<DbResourceSummary[] | null>(null)
  const [error, setError] = useState('')
  const [notBuilt, setNotBuilt] = useState(false)

  const [expandedResources, setExpandedResources] = useState<Set<string>>(new Set())
  const [expandedLetters, setExpandedLetters] = useState<Set<string>>(new Set())
  const [letterArticles, setLetterArticles] = useState<Record<string, DbArticleSummary[]>>({})
  const [loadingLetters, setLoadingLetters] = useState<Set<string>>(new Set())

  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<DbSearchHit[] | null>(null)
  const [searching, setSearching] = useState(false)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [selResources, setSelResources] = useState<Set<string>>(new Set())
  const [selLetters, setSelLetters] = useState<Set<string>>(new Set())
  const [selArticles, setSelArticles] = useState<Set<string>>(new Set())

  useEffect(() => {
    dataApi.dbIndexTree()
      .then(setTree)
      .catch((e) => { if (e?.status === 409) setNotBuilt(true); else setError(String(e)) })
  }, [])

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    if (!query.trim()) { setSearchResults(null); return }
    setSearching(true)
    searchTimer.current = setTimeout(() => {
      dataApi.dbIndexSearch(query.trim())
        .then((hits) => { setSearchResults(hits); setSearching(false) })
        .catch((e) => { setError(String(e)); setSearching(false) })
    }, 250)
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current) }
  }, [query])

  const lettersOf = (resourceId: string): { letter: string; article_count: number }[] =>
    tree?.find((r) => r.resource_id === resourceId)?.letters ?? []

  const fetchLetter = async (resourceId: string, letter: string): Promise<DbArticleSummary[]> => {
    const key = letterKey(resourceId, letter)
    if (letterArticles[key]) return letterArticles[key]
    setLoadingLetters((prev) => new Set(prev).add(key))
    try {
      const articles = await dataApi.dbIndexLetter(resourceId, letter)
      setLetterArticles((prev) => ({ ...prev, [key]: articles }))
      return articles
    } finally {
      setLoadingLetters((prev) => { const n = new Set(prev); n.delete(key); return n })
    }
  }

  const toggleExpandResource = (resourceId: string) => {
    setExpandedResources((prev) => {
      const next = new Set(prev)
      if (next.has(resourceId)) next.delete(resourceId); else next.add(resourceId)
      return next
    })
  }
  const toggleExpandLetter = (resourceId: string, letter: string) => {
    const key = letterKey(resourceId, letter)
    setExpandedLetters((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else { next.add(key); void fetchLetter(resourceId, letter) }
      return next
    })
  }

  const toggleResource = (resourceId: string) => {
    setSelResources((prev) => {
      const next = new Set(prev)
      if (next.has(resourceId)) next.delete(resourceId); else next.add(resourceId)
      return next
    })
    setSelLetters((prev) => new Set([...prev].filter((k) => !k.startsWith(resourceId + SEP))))
    setSelArticles((prev) => new Set([...prev].filter((k) => !k.startsWith(resourceId + SEP))))
  }

  const toggleLetter = (resourceId: string, letter: string) => {
    const key = letterKey(resourceId, letter)
    if (selResources.has(resourceId)) {
      // Ressource war voll ausgewählt: auf "alle anderen Buchstaben" splitten.
      const others = lettersOf(resourceId).map((l) => l.letter).filter((l) => l !== letter)
      setSelResources((prev) => { const n = new Set(prev); n.delete(resourceId); return n })
      setSelLetters((prev) => new Set([...prev, ...others.map((l) => letterKey(resourceId, l))]))
      return
    }
    setSelLetters((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
    setSelArticles((prev) => new Set([...prev].filter((k) => letterOfPath(splitKey(k)[1]) !== letter || splitKey(k)[0] !== resourceId)))
  }

  const toggleArticle = async (resourceId: string, sourcePath: string, letter: string) => {
    const key = articleKey(resourceId, sourcePath)
    const lKey = letterKey(resourceId, letter)
    const parentWasFull = selResources.has(resourceId) || selLetters.has(lKey)

    if (parentWasFull) {
      const articles = await fetchLetter(resourceId, letter)
      const siblingKeys = articles.filter((a) => a.source_path !== sourcePath).map((a) => articleKey(resourceId, a.source_path))
      if (selResources.has(resourceId)) {
        const others = lettersOf(resourceId).map((l) => l.letter).filter((l) => l !== letter)
        setSelResources((prev) => { const n = new Set(prev); n.delete(resourceId); return n })
        setSelLetters((prev) => new Set([...prev, ...others.map((l) => letterKey(resourceId, l))]))
      } else {
        setSelLetters((prev) => { const n = new Set(prev); n.delete(lKey); return n })
      }
      setSelArticles((prev) => new Set([...prev, ...siblingKeys]))
      return
    }

    setSelArticles((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  const clearSelection = () => { setSelResources(new Set()); setSelLetters(new Set()); setSelArticles(new Set()) }

  const selectedCount = useMemo(() => {
    let n = 0
    for (const r of selResources) n += tree?.find((x) => x.resource_id === r)?.article_count ?? 0
    for (const k of selLetters) {
      const [r, l] = splitKey(k)
      n += tree?.find((x) => x.resource_id === r)?.letters.find((y) => y.letter === l)?.article_count ?? 0
    }
    n += selArticles.size
    return n
  }, [tree, selResources, selLetters, selArticles])

  useEffect(() => {
    const selection: DbSelection = {
      resource_ids: [...selResources],
      resource_letters: [...selLetters].map((k) => splitKey(k)),
      articles: [...selArticles].map((k) => splitKey(k)),
    }
    onSelectionChange(selection, selectedCount)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selResources, selLetters, selArticles, selectedCount])

  if (error) return <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-err)' }}>{error}</div>
  if (notBuilt) {
    return (
      <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)', lineHeight: 1.5 }}>
        Noch kein Artikelindex aufgebaut. Ein Administrator kann ihn im Admin-Bereich anlegen
        (Schaltfläche „Jetzt neu aufbauen").
      </div>
    )
  }
  if (tree === null) return <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)' }}>Lädt…</div>
  if (tree.length === 0) return <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)' }}>Keine Wörterbücher freigegeben.</div>

  const isSearching = query.trim() !== ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minHeight: 0 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '0 2px' }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <Icon name="search" size={12} style={{ position: 'absolute', left: 8, top: 8, color: 'var(--lt-fg-4)' }} />
          <input
            value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Lemma oder Artikel-ID durchsuchen…"
            style={{
              width: '100%', boxSizing: 'border-box', padding: '6px 9px 6px 26px', fontSize: 12,
              background: 'var(--lt-bg-1)', border: '1px solid var(--lt-line-1)',
              borderRadius: 'var(--lt-r-sm)', color: 'var(--lt-fg-1)', outline: 'none',
            }}
          />
        </div>
        {selectedCount > 0 && (
          <button onClick={clearSelection} style={{
            fontSize: 11, color: 'var(--lt-fg-3)', background: 'none', border: '1px solid var(--lt-line-1)',
            borderRadius: 'var(--lt-r-sm)', padding: '5px 9px', cursor: 'pointer', whiteSpace: 'nowrap',
          }}>Auswahl aufheben</button>
        )}
      </div>

      <div style={{ maxHeight: '46vh', overflowY: 'auto', border: '1px solid var(--lt-line-1)', borderRadius: 'var(--lt-r-sm)', padding: 4 }}>
        {isSearching ? (
          searching ? <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)' }}>Sucht…</div>
          : searchResults && searchResults.length === 0 ? <div style={{ padding: 12, fontSize: 12, color: 'var(--lt-fg-3)' }}>Keine Treffer.</div>
          : (searchResults ?? []).map((hit) => {
              const key = articleKey(hit.resource_id, hit.source_path)
              const checked = selArticles.has(key) || selLetters.has(letterKey(hit.resource_id, hit.letter)) || selResources.has(hit.resource_id)
              return (
                <label key={key} style={row}>
                  <span style={{ width: 16, flexShrink: 0 }} />
                  <input type="checkbox" checked={checked} onChange={() => void toggleArticle(hit.resource_id, hit.source_path, hit.letter)} />
                  <Icon name="file" size={12} style={{ color: 'var(--lt-fg-4)', flexShrink: 0 }} />
                  <span style={rowLabel}>
                    {hit.lemma ?? hit.article_id}
                    <span style={{ color: 'var(--lt-fg-4)', marginLeft: 6, fontSize: 11 }}>{hit.resource_id} / {hit.letter}</span>
                  </span>
                </label>
              )
            })
        ) : (
          tree.map((r) => {
            const rExpanded = expandedResources.has(r.resource_id)
            const rChecked = selResources.has(r.resource_id)
            return (
              <div key={r.resource_id}>
                <label style={row}>
                  <Chevron expanded={rExpanded} onClick={() => toggleExpandResource(r.resource_id)} />
                  <input type="checkbox" checked={rChecked} onChange={() => toggleResource(r.resource_id)} />
                  <Icon name="book" size={13} style={{ color: 'var(--lt-primary)', flexShrink: 0 }} />
                  <span style={rowLabel}>{r.resource_id}</span>
                  <span style={rowCount}>{r.article_count} Artikel</span>
                </label>
                {rExpanded && r.letters.map((l) => {
                  const lKey = letterKey(r.resource_id, l.letter)
                  const lExpanded = expandedLetters.has(lKey)
                  const lChecked = rChecked || selLetters.has(lKey)
                  const articles = letterArticles[lKey]
                  return (
                    <div key={lKey}>
                      <label style={{ ...row, paddingLeft: 24 }}>
                        <Chevron expanded={lExpanded} onClick={() => toggleExpandLetter(r.resource_id, l.letter)} />
                        <input type="checkbox" checked={lChecked} onChange={() => toggleLetter(r.resource_id, l.letter)} />
                        <span style={{ ...rowLabel, fontFamily: 'var(--lt-font-mono)' }}>{l.letter}</span>
                        <span style={rowCount}>{l.article_count} Artikel</span>
                      </label>
                      {lExpanded && (
                        loadingLetters.has(lKey) ? (
                          <div style={{ padding: '4px 8px 4px 46px', fontSize: 11, color: 'var(--lt-fg-4)' }}>Lädt…</div>
                        ) : (articles ?? []).map((a) => {
                          const aKey = articleKey(r.resource_id, a.source_path)
                          const aChecked = lChecked || selArticles.has(aKey)
                          return (
                            <label key={aKey} style={{ ...row, paddingLeft: 46 }}>
                              <input type="checkbox" checked={aChecked} onChange={() => void toggleArticle(r.resource_id, a.source_path, l.letter)} />
                              <Icon name="file" size={12} style={{ color: 'var(--lt-fg-4)', flexShrink: 0 }} />
                              <span style={rowLabel}>{a.lemma ?? a.article_id}</span>
                            </label>
                          )
                        })
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
