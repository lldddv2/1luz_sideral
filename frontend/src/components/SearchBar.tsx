import { useEffect, useRef, useState } from 'react'
import { Loader2, MapPin, Plus, Search, X } from 'lucide-react'
import { searchPlaces } from '../nominatim'
import type { PlaceResult } from '../nominatim'

interface Props {
  onPreview: (result: PlaceResult) => void // fly to the result; draw its outline if it has one
  onAdd: (result: PlaceResult) => void // add the result as a region shape
}

// Nominatim allows one request per second. Search runs on Enter or the button only, never while a request is pending.
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

export default function SearchBar({ onPreview, onAdd }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlaceResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [activeId, setActiveId] = useState<PlaceResult['id'] | null>(null)
  const controller = useRef<AbortController | null>(null)
  const lastStart = useRef(0)
  const root = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

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
    if (!q || loading) return
    const ac = new AbortController()
    controller.current = ac
    setLoading(true)
    setError(null)
    setOpen(true)
    try {
      const delay = MIN_INTERVAL_MS - (Date.now() - lastStart.current)
      if (delay > 0) await sleep(delay, ac.signal)
      lastStart.current = Date.now()
      setResults(await searchPlaces(q, ac.signal))
    } catch (err) {
      if (ac.signal.aborted) return
      setResults(null)
      setError(`No se pudo buscar (${err instanceof Error ? err.message : String(err)}).`)
    } finally {
      if (!ac.signal.aborted) setLoading(false)
    }
  }

  return (
    <div
      ref={root}
      className={`search-bar${open && (loading || error || results) ? ' is-open' : ''}`}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
        // MapView listens on window for Enter, Backspace and Escape (drawing and selection); keep typing here out of it.
        e.stopPropagation()
      }}
    >
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
          placeholder="Buscar lugar…"
          aria-label="Buscar lugar"
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
      {open && (loading || error || results) && (
        <ul className="search-results">
          {loading && <li className="search-status">Buscando…</li>}
          {!loading && error && <li className="search-status search-error">{error}</li>}
          {!loading && results?.length === 0 && <li className="search-status">Sin resultados.</li>}
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
        </ul>
      )}
    </div>
  )
}
