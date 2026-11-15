import { useEffect, useRef, useState } from 'react'
import { CalendarDays, Circle, Loader2, MapPin, Mountain, Plus, Search, Tags, X } from 'lucide-react'
import { geometryBox, placeInAreas, searchPlaces, unionBox } from '../nominatim'
import type { PlaceResult } from '../nominatim'
import type { RegionGeometry } from '../types'
import { yesterdayIso } from '../download'
import { formatPercent, matchCover } from '../landcover'
import type { CoverSuggestions } from '../landcover'
import { CATEGORY_COLOR, fetchFeatures, groupLabel } from '../features'
import type { NaturalFeature } from '../features'

interface Props {
  start: string // YYYY-MM-DD, the download range shared with the sidebar
  end: string // YYYY-MM-DD, the download range shared with the sidebar
  onDatesChange: (patch: { start?: string; end?: string }) => void
  onPreview: (result: PlaceResult) => void // fly to the result; draw its outline if it has one
  onAdd: (result: PlaceResult) => void // add the result as a region shape
  coverSuggestions: CoverSuggestions // land-cover classes for the query, with the active area's stats
  onPickCover: (key: string) => void // toggles a class in the map filter
  onPickFeature: (feature: NaturalFeature) => void // fly to a natural feature and outline its bbox
  onAddFeature: (feature: NaturalFeature) => void // add the feature's bbox as a study area
  onShowFeatures: (features: NaturalFeature[]) => void // label these features on the map
  areaShapes: RegionGeometry[] // study areas; when present, natural features and places are limited to them
}

// Natural features come from our own backend, so they can follow the typing (debounced).
const FEATURE_DEBOUNCE_MS = 250

// Regions go through the backend (which rate-limits Nominatim to 1 req/s and caches), so they also follow typing.
const REGION_DEBOUNCE_MS = 450
const MIN_INTERVAL_MS = 1000

// Resolves after ms; rejects early if the signal aborts.
const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
  })

export default function SearchBar({ start, end, onDatesChange, onPreview, onAdd, coverSuggestions, onPickCover, onPickFeature, onAddFeature, onShowFeatures, areaShapes }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlaceResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [activeId, setActiveId] = useState<PlaceResult['id'] | null>(null)
  const [natural, setNatural] = useState<NaturalFeature[]>([])
  const [naturalEmpty, setNaturalEmpty] = useState(false) // nothing in the selected areas
  const [worldwide, setWorldwide] = useState(false) // user chose to ignore the areas
  const controller = useRef<AbortController | null>(null)
  const lastStart = useRef(0)
  const root = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  // Cover matches are local and instant, so they show while typing; places wait for Enter as before.
  const { classes, classesError, filter, area } = coverSuggestions
  const matched = matchCover(query)
  const coverRows = classes.filter((cls) => matched.includes(cls.key))
  // Land cover is secondary now: only offered once an area exists.
  const showCover = area !== null && matched.length > 0 && (coverRows.length > 0 || classesError !== null)
  const showNatural = natural.length > 0
  const boxKey = worldwide || areaShapes.length === 0 ? '' : JSON.stringify(areaShapes)
  const scoped = boxKey !== ''
  // Places found worldwide but none inside the areas: offer the worldwide search.
  const placesEmpty = scoped && !loading && !error && results?.length === 0
  const listOpen = open && (loading || error || results || showCover || showNatural || naturalEmpty)

  // Natural features (global catalog): a category word lists the whole category, otherwise names match.
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setNatural([])
      setNaturalEmpty(false)
      return
    }
    const boxes: RegionGeometry[] = boxKey ? JSON.parse(boxKey) : []
    const ac = new AbortController()
    const timer = setTimeout(() => {
      fetchFeatures(q, boxes, ac.signal)
        .then((list) => {
          setNatural(list)
          // Only worth saying when the areas hid something.
          setNaturalEmpty(list.length === 0 && boxes.length > 0)
        })
        .catch(() => {
          if (ac.signal.aborted) return
          setNatural([])
          setNaturalEmpty(false)
        })
    }, FEATURE_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ac.abort()
    }
  }, [query, boxKey])

  // Regions (countries, departments, municipalities) follow the typing too, debounced.
  // A change of areas (or the worldwide switch) searches again with the new scope.
  useEffect(() => {
    if (query.trim().length < 2) return
    const timer = setTimeout(() => searchRef.current(), REGION_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [query, boxKey])

  // A new query or a change of areas goes back to area-limited results.
  useEffect(() => setWorldwide(false), [query, areaShapes.length])

  // Cancel the pending request on unmount.
  useEffect(() => () => controller.current?.abort(), [])

  // Ctrl/Cmd+K focuses the search; a click outside closes the results.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        input.current?.focus()
        input.current?.select()
      }
    }
    const onDown = (e: PointerEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onDown)
    }
  }, [])

  const clear = () => {
    controller.current?.abort()
    setQuery('')
    setResults(null)
    setError(null)
    setLoading(false)
    setActiveId(null)
    input.current?.focus()
  }

  const search = async () => {
    const q = query.trim()
    if (!q) return
    controller.current?.abort()
    const ac = new AbortController()
    controller.current = ac
    setLoading(true)
    setError(null)
    setOpen(true)
    try {
      const delay = MIN_INTERVAL_MS - (Date.now() - lastStart.current)
      if (delay > 0) await sleep(delay, ac.signal)
      lastStart.current = Date.now()
      // With study areas, Nominatim searches their combined box; the shapes then trim what lies between them.
      const areas: RegionGeometry[] = boxKey ? JSON.parse(boxKey) : []
      const viewbox = unionBox(areas.map(geometryBox)) ?? undefined
      const found = await searchPlaces(q, ac.signal, viewbox)
      setResults(areas.length ? found.filter((r) => placeInAreas(r, areas)) : found)
    } catch (err) {
      if (ac.signal.aborted) return
      setResults(null)
      setError(`No se pudo buscar (${err instanceof Error ? err.message : String(err)}).`)
    } finally {
      if (!ac.signal.aborted) setLoading(false)
    }
  }

  const searchRef = useRef(search)
  searchRef.current = search

  // Same date limits as the sidebar: no date after yesterday; the start may not pass the end.
  const latest = yesterdayIso()
  const startMax = end && end < latest ? end : latest
  // Same rule as datesOk in useDownload.
  const datesOk = start !== '' && end !== '' && start <= end

  return (
    <div
      ref={root}
      className={`search-bar${listOpen ? ' is-open' : ''}`}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
        // MapView listens on window for Enter, Backspace and Escape (drawing and selection); keep typing here out of it.
        e.stopPropagation()
      }}
    >
      <div className="search-top">
      <form
        className="search-form"
        onSubmit={(e) => {
          e.preventDefault()
          search()
        }}
      >
        <span className="search-icon" aria-hidden="true">
          {loading ? <Loader2 size={17} className="spin" /> : <Search size={17} />}
        </span>
        <input
          ref={input}
          className="search-input"
          type="text"
          placeholder="Buscar lugar, humedales, glaciares, desiertos…"
          aria-label="Buscar lugar o cobertura"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
        />
        {query ? (
          <button type="button" className="search-clear" aria-label="Limpiar búsqueda" onClick={clear}>
            <X size={15} />
          </button>
        ) : (
          <kbd className="search-kbd">Ctrl K</kbd>
        )}
        <button type="submit" className="search-submit" aria-label="Buscar" disabled={loading || !query.trim()}>
          <Search size={15} />
        </button>
      </form>
      <div className={`search-dates${datesOk ? '' : ' is-invalid'}`}>
        <CalendarDays size={16} aria-hidden="true" />
        <input
          className="search-date"
          type="date"
          aria-label="Fecha inicial"
          aria-invalid={!datesOk}
          max={startMax}
          value={start}
          onChange={(e) => onDatesChange({ start: e.target.value })}
        />
        <span className="search-dates-sep" aria-hidden="true">–</span>
        <input
          className="search-date"
          type="date"
          aria-label="Fecha final"
          aria-invalid={!datesOk}
          min={start || undefined}
          max={latest}
          value={end}
          onChange={(e) => onDatesChange({ end: e.target.value })}
        />
      </div>
      </div>
      {listOpen && (
        <ul className="search-results">
          {showNatural && <li className="search-group">{groupLabel(natural)} ({scoped ? 'en el área' : 'mundo'})</li>}
          {naturalEmpty && <li className="search-status">Ningún lugar natural en el área seleccionada.</li>}
          {showNatural && natural.length > 1 && (
            <li className="search-row">
              <button
                type="button"
                className="search-row-main"
                title="Mostrar una etiqueta por lugar en el mapa"
                onClick={() => {
                  onShowFeatures(natural)
                  setOpen(false)
                }}
              >
                <Tags size={16} aria-hidden="true" />
                <span className="search-text">
                  <span className="search-name">
                    Mostrar {natural.length} {groupLabel(natural).toLowerCase()} en el mapa
                  </span>
                </span>
              </button>
            </li>
          )}
          {showNatural &&
            natural.slice(0, 12).map((f) => (
              <li key={`${f.category}:${f.name}`} className="search-row">
                <button
                  type="button"
                  className="search-row-main"
                  title={`Ir a ${f.name}`}
                  onClick={() => {
                    onShowFeatures([f])
                    onPickFeature(f)
                    setOpen(false)
                  }}
                >
                  <Mountain size={16} color={CATEGORY_COLOR[f.category]} aria-hidden="true" />
                  <span className="search-text">
                    <span className="search-name">{f.name}</span>
                    <span className="search-type">{f.category_name}</span>
                  </span>
                </button>
                <button
                  type="button"
                  className="search-add"
                  title="Agregar como área de estudio"
                  aria-label={`Agregar ${f.name} como área de estudio`}
                  onClick={() => {
                    onAddFeature(f)
                    setOpen(false)
                  }}
                >
                  <Plus size={16} />
                </button>
              </li>
            ))}
          {showCover && (
            <li className={`search-group${area ? '' : ' is-disabled'}`}>
              {area ? `Coberturas en ${area.name}` : 'Coberturas'}
            </li>
          )}
          {showCover && classesError && <li className="search-status search-error">Error: {classesError}</li>}
          {showCover &&
            area &&
            coverRows.map((cls) => {
              const on = filter.includes(cls.key)
              const entry = area.stats
              const percent =
                entry?.status === 'ready' ? entry.stats.classes.find((c) => c.key === cls.key)?.percent : undefined
              return (
                <li key={cls.key} className={`search-row${on ? ' is-active' : ''}`}>
                  <button
                    type="button"
                    className="search-row-main"
                    aria-pressed={on}
                    title={on ? `Quitar ${cls.name} del filtro` : `Filtrar el mapa por ${cls.name}`}
                    onClick={() => {
                      onPickCover(cls.key)
                      setQuery('')
                      setOpen(false)
                    }}
                  >
                    <Circle size={16} fill={cls.color} stroke={cls.color} aria-hidden="true" />
                    <span className="search-text">
                      <span className="search-name">{cls.name}</span>
                    </span>
                    {percent !== undefined && <span className="cover-percent">{formatPercent(percent)}</span>}
                    {percent === undefined && entry?.status === 'loading' && (
                      <Loader2 size={16} className="spin cover-wait" aria-hidden="true" />
                    )}
                  </button>
                </li>
              )
            })}
          {(loading || error || results) && (
            <li className="search-group">Lugares ({scoped ? 'en el área' : 'mundo'})</li>
          )}
          {loading && <li className="search-status">Buscando…</li>}
          {!loading && error && <li className="search-status search-error">{error}</li>}
          {placesEmpty && <li className="search-status">Ningún lugar en el área seleccionada.</li>}
          {!loading && !scoped && results?.length === 0 && <li className="search-status">Sin resultados.</li>}
          {!loading &&
            results?.map((r) => (
              <li key={r.id} className={`search-row${activeId === r.id ? ' is-active' : ''}`}>
                <button
                  type="button"
                  className="search-row-main"
                  title={r.label}
                  onClick={() => {
                    setActiveId(r.id)
                    onPreview(r)
                    setOpen(false)
                  }}
                >
                  <MapPin size={16} />
                  <span className="search-text">
                    <span className="search-name">{r.name}</span>
                    <span className="search-type">{r.type}</span>
                  </span>
                </button>
                {r.geometry && (
                  <button
                    type="button"
                    className="search-add"
                    title="Agregar como área de estudio"
                    aria-label={`Agregar ${r.name} como área de estudio`}
                    onClick={() => {
                      onAdd(r)
                      setOpen(false)
                    }}
                  >
                    <Plus size={16} />
                  </button>
                )}
              </li>
            ))}
          {/* One switch for both lists: natural features and places go worldwide together. */}
          {(naturalEmpty || placesEmpty) && (
            <li className="search-row">
              <button type="button" className="search-row-main" onClick={() => setWorldwide(true)}>
                <Search size={16} aria-hidden="true" />
                <span className="search-text">
                  <span className="search-name">Buscar en todo el mundo</span>
                </span>
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
