import { useEffect, useRef, useState } from 'react'
import { shapeGeometry } from './geo'
import { messageOf } from './download'
import { areaOfKey, fetchPasses, passKey, searchRange } from './passes'
import type { DateRange, PassEntry } from './passes'
import type { AoiPolygon } from './types'

// Radar passes of the active area (the last one, as Descarga uses) over the Descarga range. The search covers
// the default window when the range lies inside it, else the range itself. Results are cached per area and
// window. A deleted area drops its results, and its response is dropped if still in flight.
export function usePasses(areas: AoiPolygon[], range: DateRange | null): PassEntry | undefined {
  const [entries, setEntries] = useState<Record<string, PassEntry>>({})
  const requests = useRef(new Map<string, AbortController>())
  const active = areas.at(-1) ?? null
  const key = active && range ? passKey(active.id, searchRange(range)) : null

  useEffect(() => {
    const live = new Set(areas.map((a) => a.id))
    for (const [k, controller] of requests.current) {
      if (live.has(areaOfKey(k))) continue
      controller.abort()
      requests.current.delete(k)
    }
    setEntries((prev) => {
      const kept = Object.keys(prev).filter((k) => live.has(areaOfKey(k)))
      return kept.length === Object.keys(prev).length ? prev : Object.fromEntries(kept.map((k) => [k, prev[k]]))
    })
  }, [areas])

  useEffect(() => {
    if (!active || !range || !key || requests.current.has(key)) return
    const controller = new AbortController()
    requests.current.set(key, controller)
    const settle = (entry: PassEntry) => {
      if (!controller.signal.aborted) setEntries((prev) => ({ ...prev, [key]: entry }))
    }
    setEntries((prev) => ({ ...prev, [key]: { status: 'loading' } }))
    fetchPasses(shapeGeometry(active), searchRange(range), controller.signal).then(
      (products) => settle({ status: 'ready', products }),
      (err) => settle({ status: 'error', message: messageOf(err) }),
    )
  }, [active, range, key])

  return key ? entries[key] : undefined
}
