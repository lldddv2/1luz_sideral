import { DEFAULT_START, searchProducts, todayIso } from './download'
import type { FlightDirection, RegionGeometry, SearchProduct } from './types'

// Passes per area: the backend default, searched over the default window or over the Download range.
const PASS_MAX_RESULTS = 100
const DAY_MS = 24 * 60 * 60 * 1000
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DIRECTION_SHORT: Record<FlightDirection, string> = { ascending: 'Asc', descending: 'Desc' }

// Colors per group; the palette wraps when an area crosses more groups than colors.
const PALETTE = ['#2563eb', '#059669', '#9333ea', '#db2777', '#0891b2', '#65a30d', '#4f46e5', '#b91c1c']

// Share of the axis kept free around each axis label. Edge labels are wider than month labels.
const LABEL_GAP = 0.2

// Calendar days, YYYY-MM-DD, both ends included.
export interface DateRange {
  start: string
  end: string
}

export type PassEntry =
  | { status: 'loading' }
  | { status: 'ready'; products: SearchProduct[] }
  | { status: 'error'; message: string }

export interface PassGroup {
  key: string
  track: number | null
  direction: FlightDirection | null
  color: string
  products: SearchProduct[] // newest first
}

// Window searched for a Download range: the default window when the range lies inside it, else the range.
// The default window runs from DEFAULT_START to today.
export function searchRange(range: DateRange): DateRange {
  const base = { start: DEFAULT_START, end: todayIso() }
  return range.start >= base.start && range.end <= base.end ? base : range
}

// Cache key of a search: area id and window. Area ids are UUIDs, so they hold no '|'.
export const passKey = (areaId: string, search: DateRange) => `${areaId}|${search.start}|${search.end}`
export const areaOfKey = (key: string) => key.split('|')[0]

export const fetchPasses = (geometry: RegionGeometry, search: DateRange, signal: AbortSignal) =>
  searchProducts(
    geometry,
    `${search.start}T00:00:00Z`,
    `${search.end}T23:59:59Z`,
    PASS_MAX_RESULTS,
    signal,
  ).then((result) => result.products)

// Epoch ms of a range: from the start of its first day to the end of its last day.
export const rangeBounds = (range: DateRange) => ({
  start: Date.parse(`${range.start}T00:00:00Z`),
  end: Date.parse(`${range.end}T00:00:00Z`) + DAY_MS,
})

// Acquisition start in epoch ms; NaN when the product has none.
export const timeMs = (p: SearchProduct) => Date.parse(p.acquisition_start ?? '')
const timeOf = (p: SearchProduct) => timeMs(p) || 0
const trackRank = (track: number | null) => track ?? Number.MAX_SAFE_INTEGER
const directionRank = (direction: FlightDirection | null) =>
  direction === 'ascending' ? 0 : direction === 'descending' ? 1 : 2

// Products grouped by track and direction: by track, then ascending before descending.
export function groupPasses(products: SearchProduct[]): PassGroup[] {
  const byKey = new Map<string, SearchProduct[]>()
  for (const p of products) {
    const key = `${p.track ?? ''}/${p.direction ?? ''}`
    byKey.set(key, [...(byKey.get(key) ?? []), p])
  }
  return [...byKey]
    .map(([key, list]) => ({
      key,
      track: list[0].track,
      direction: list[0].direction,
      products: [...list].sort((a, b) => timeOf(b) - timeOf(a)),
    }))
    .sort((a, b) => trackRank(a.track) - trackRank(b.track) || directionRank(a.direction) - directionRank(b.direction))
    .map((group, i) => ({ ...group, color: PALETTE[i % PALETTE.length] }))
}

// Passes inside the range, grouped as groupPasses does. Colors come from all products, so they hold when the range moves.
export function groupsIn(products: SearchProduct[], range: DateRange): PassGroup[] {
  const { start, end } = rangeBounds(range)
  const inside = (p: SearchProduct) => {
    const t = timeMs(p)
    return t >= start && t < end
  }
  return groupPasses(products)
    .map((group) => ({ ...group, products: group.products.filter(inside) }))
    .filter((group) => group.products.length > 0)
}

const pad = (n: number) => String(n).padStart(2, '0')

// Short UTC day, e.g. 30 Oct.
export function shortDay(ms: number): string {
  const d = new Date(ms)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
}

// UTC day with year, e.g. 30 Oct 2026.
const fullDay = (ms: number) => `${shortDay(ms)} ${new Date(ms).getUTCFullYear()}`

// UTC day and time, e.g. 30 Oct 2026 · 12:03 UTC; '—' when there is no time.
export function utcLabel(iso: string | null): string {
  const time = iso === null ? NaN : Date.parse(iso)
  if (Number.isNaN(time)) return '—'
  const d = new Date(time)
  return `${fullDay(time)} · ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`
}

// Track and direction, e.g. Asc 019; the track alone when the direction is unknown.
export function orbitName({ track, direction }: PassGroup): string {
  const number = track === null ? '—' : String(track).padStart(3, '0')
  return direction ? `${DIRECTION_SHORT[direction]} ${number}` : number
}

export interface AxisLabel {
  f: number // share of the axis, 0 to 1
  text: string
  align: 'start' | 'middle' | 'end' // edges align to the axis ends; months center on their tick
}

// Labels of a range axis: its first and last day at the ends, and the month starts between them.
// A month label is dropped when it would crowd the label before it or an edge label.
export function axisLabels(range: DateRange): AxisLabel[] {
  const { start, end } = rangeBounds(range)
  const place = (t: number) => (t - start) / (end - start)
  const labels: AxisLabel[] = [
    { f: 0, text: fullDay(start), align: 'start' },
    { f: 1, text: fullDay(end - DAY_MS), align: 'end' },
  ]
  const first = new Date(start)
  let last = 0
  let t = Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 1)
  while (t < end) {
    const d = new Date(t)
    const f = place(t)
    if (f - last >= LABEL_GAP && 1 - f >= LABEL_GAP) {
      labels.push({ f, text: `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`, align: 'middle' })
      last = f
    }
    t = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1)
  }
  return labels
}

// Median gap in days between consecutive passes of one track and direction. A gap under a day is one pass
// seen in two frames, not a revisit. Null when no revisit exists.
export function revisitDays(groups: PassGroup[]): number | null {
  const gaps: number[] = []
  for (const g of groups) {
    const times = g.products.map(timeMs).filter(Number.isFinite).sort((a, b) => a - b)
    for (let i = 1; i < times.length; i++) {
      const gap = (times[i] - times[i - 1]) / DAY_MS
      if (gap >= 1) gaps.push(gap)
    }
  }
  if (gaps.length === 0) return null
  gaps.sort((a, b) => a - b)
  const mid = Math.floor(gaps.length / 2)
  return gaps.length % 2 === 1 ? gaps[mid] : (gaps[mid - 1] + gaps[mid]) / 2
}

// One line over the timeline: acquisition count and median revisit, e.g. 12 acquisitions · median revisit 12 days.
export function passSummary(groups: PassGroup[]): string {
  const n = groups.reduce((sum, g) => sum + g.products.length, 0)
  const parts = [`${n} ${n === 1 ? 'acquisition' : 'acquisitions'}`]
  const revisit = revisitDays(groups)
  if (revisit !== null) {
    const days = Math.round(revisit)
    parts.push(`median revisit ${days} ${days === 1 ? 'day' : 'days'}`)
  }
  return parts.join(' · ')
}
