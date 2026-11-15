import { useEffect, useRef, useState } from 'react'
import { shapeGeometry } from './geo'
import { messageOf } from './download'
import { fetchClasses, fetchMask, fetchStats } from './landcover'
import type { CoverChip, CoverMaskImage, CoverSuggestions, LandcoverClass, StatsEntry } from './landcover'
import type { AoiPolygon } from './types'

export interface LandcoverController {
  suggestions: CoverSuggestions
  chips: CoverChip[]
  toggle: (key: string) => void // adds the class to the filter, or removes it
  mask: CoverMaskImage | null // drawn over the map; null while loading, on error, or without filter
  maskLoading: boolean
  maskError: string | null
}

type MaskState =
  | { key: string; status: 'loading' }
  | { key: string; status: 'ready'; image: CoverMaskImage }
  | { key: string; status: 'error'; message: string }

// Land-cover filter. The class table loads once. Stats are cached per area id and requested in the background
// when the active area appears (the last area, as Descarga uses). The mask follows the active area and the chips:
// its key is the area id plus the sorted class keys, so a result for an older key is dropped. A deleted area drops
// its stats and aborts its request. Edits that move an area keep its id, so its stats and mask do not refresh.
export function useLandcover(areas: AoiPolygon[]): LandcoverController {
  const [classes, setClasses] = useState<LandcoverClass[]>([])
  const [classesError, setClassesError] = useState<string | null>(null)
  const [stats, setStats] = useState<Record<string, StatsEntry>>({})
  const [filter, setFilter] = useState<string[]>([])
  const [mask, setMask] = useState<MaskState | null>(null)
  const requests = useRef(new Map<string, AbortController>())
  const active = areas.at(-1) ?? null
  const activeId = active?.id ?? null
  const activeReady = activeId !== null && stats[activeId]?.status === 'ready'
  const classesKey = [...filter].sort().join(',')
  const maskKey = active && classesKey ? `${active.id}|${classesKey}` : null

  useEffect(() => {
    const controller = new AbortController()
    fetchClasses(controller.signal).then(setClasses, (err) => {
      if (!controller.signal.aborted) setClassesError(messageOf(err))
    })
    return () => controller.abort()
  }, [])

  // Deleted areas drop their stats; a request still in flight for one is aborted.
  useEffect(() => {
    const live = new Set(areas.map((a) => a.id))
    for (const [id, controller] of requests.current) {
      if (live.has(id)) continue
      controller.abort()
      requests.current.delete(id)
    }
    setStats((prev) => {
      const ids = Object.keys(prev)
      const kept = ids.filter((id) => live.has(id))
      return kept.length === ids.length ? prev : Object.fromEntries(kept.map((id) => [id, prev[id]]))
    })
  }, [areas])

  // Stats of the active area, requested as soon as it exists. A failed request is retried when the active area object changes.
  useEffect(() => {
    if (!active || activeReady || requests.current.has(active.id)) return
    const { id } = active
    const controller = new AbortController()
    requests.current.set(id, controller)
    const settle = (entry: StatsEntry) => {
      if (requests.current.get(id) === controller) requests.current.delete(id)
      if (!controller.signal.aborted) setStats((prev) => ({ ...prev, [id]: entry }))
    }
    setStats((prev) => ({ ...prev, [id]: { status: 'loading' } }))
    fetchStats(shapeGeometry(active), controller.signal).then(
      (result) => settle({ status: 'ready', stats: result }),
      (err) => settle({ status: 'error', message: messageOf(err) }),
    )
  }, [active, activeReady])

  // Mask of the active area for the chips. Cleanup aborts the request when the key changes.
  useEffect(() => {
    if (!active || !maskKey) {
      setMask(null)
      return
    }
    const controller = new AbortController()
    const key = maskKey
    setMask({ key, status: 'loading' })
    fetchMask(shapeGeometry(active), classesKey.split(','), controller.signal).then(
      (image) => {
        if (!controller.signal.aborted) setMask({ key, status: 'ready', image })
      },
      (err) => {
        if (!controller.signal.aborted) setMask({ key, status: 'error', message: messageOf(err) })
      },
    )
    return () => controller.abort()
  }, [maskKey])

  const toggle = (key: string) =>
    setFilter((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]))

  const activeStats = activeId !== null ? stats[activeId] : undefined
  const percentOf = (key: string): number | null =>
    activeStats?.status === 'ready' ? (activeStats.stats.classes.find((c) => c.key === key)?.percent ?? null) : null
  const chips: CoverChip[] = filter.map((key) => {
    const cls = classes.find((c) => c.key === key)
    return { key, name: cls?.name ?? key, color: cls?.color ?? '#6b7280', percent: percentOf(key) }
  })

  const current = mask && mask.key === maskKey ? mask : null

  return {
    suggestions: {
      classes,
      classesError,
      filter,
      area: active ? { name: active.name, stats: activeStats } : null,
    },
    chips,
    toggle,
    mask: current?.status === 'ready' ? current.image : null,
    maskLoading: current?.status === 'loading',
    maskError: current?.status === 'error' ? current.message : null,
  }
}
