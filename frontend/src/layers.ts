// Water-scenario overlays drawn on top of the basemap (raster XYZ tiles, keyless).
export type OverlayId = 'dswx' | 'nisar' | 'jrc'

export interface Overlay {
  id: OverlayId
  label: string
  hint: string
  tiles: string // XYZ template; GIBS layers contain {time}
  maxzoom: number
  attribution: string
  needsDate: boolean
}

export interface OverlayState {
  on: boolean
  opacity: number // 0..100
  date: string // YYYY-MM-DD for GIBS daily layers; GIBS tiles only cover that day's swaths
  mode?: NisarMode // NISAR only
  outline?: boolean // NISAR only: swath outline when zoomed out
  asc?: boolean // NISAR only: show ascending passes (default true)
  desc?: boolean // NISAR only: show descending passes (default true)
}

// 'water' = thresholded low-backscatter mask; 'color' = softened false-color preview.
export type NisarMode = 'water' | 'color'

const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best'

export const OVERLAYS: Record<OverlayId, Overlay> = {
  dswx: {
    id: 'dswx',
    label: 'OPERA DSWx-S1',
    hint: 'Surface water (Sentinel-1, C-band); 12-day mosaic, newest pass wins',
    tiles: `${GIBS}/OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1/default/{time}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png`,
    maxzoom: 12,
    attribution: 'OPERA DSWx-S1 · NASA GIBS',
    needsDate: true,
  },
  nisar: {
    id: 'nisar',
    label: 'NISAR GCOV (preview)',
    hint: 'L-band backscatter from GIBS; uses the nearest valid date',
    tiles: `${GIBS}/NISAR_L2_Geocoded_Polarimetric_Covariance/default/{time}/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png`,
    maxzoom: 13,
    attribution: 'NISAR GCOV · NASA-ISRO · NASA GIBS',
    needsDate: true,
  },
  jrc: {
    id: 'jrc',
    label: 'JRC historical water',
    hint: 'Water occurrence 1984–2021; separates permanent water from flooding',
    tiles: 'https://storage.googleapis.com/global-surface-water/tiles2021/occurrence/{z}/{x}/{y}.png',
    maxzoom: 13,
    attribution: 'EC JRC / Google Global Surface Water',
    needsDate: false,
  },
}

export const OVERLAY_IDS: OverlayId[] = ['dswx', 'nisar', 'jrc']

export const DEFAULT_OVERLAYS: Record<OverlayId, OverlayState> = {
  // Defaults are days with verified pixels over La Mojana (Colombia); most single days are empty there.
  dswx: { on: false, opacity: 70, date: '2026-11-14' },
  nisar: { on: false, opacity: 80, date: '2026-11-01', mode: 'color', outline: true, asc: true, desc: true },
  jrc: { on: false, opacity: 70, date: '' },
}

// NISAR GCOV availability in GIBS (from GetCapabilities); last range is open-ended.
const NISAR_RANGES: [string, string][] = [
  ['2025-10-29', '2026-03-01'],
  ['2026-03-04', '2026-03-29'],
  ['2026-04-01', '2026-04-12'],
  ['2026-04-14', '2026-07-27'],
  ['2026-08-10', '9999-12-31'],
]

const days = (iso: string) => Date.parse(iso + 'T00:00:00Z') / 86400000

// Snaps a date into a NISAR range, picking the closest valid day when it falls in a gap.
export function nisarDate(iso: string): string {
  let best = NISAR_RANGES[0][0]
  let bestGap = Infinity
  for (const [a, b] of NISAR_RANGES) {
    if (iso >= a && iso <= b) return iso
    const gap = iso < a ? days(a) - days(iso) : days(iso) - days(b)
    if (gap < bestGap) {
      bestGap = gap
      best = iso < a ? a : b
    }
  }
  return best
}

// Tile URL for a layer at a given date (YYYY-MM-DD).
export function overlayTiles(id: OverlayId, date: string): string {
  const o = OVERLAYS[id]
  if (!o.needsDate) return o.tiles
  return o.tiles.replace('{time}', id === 'nisar' ? nisarDate(date) : date)
}

// GIBS NISAR GCOV false color: red = co-pol (HH or VV), green = cross-pol (HV or VH),
// blue = co-pol (lower stretch). Open water is specular at L-band, so all channels are dark.
// Threshold picked on La Mojana tile 9/243/149 (2026-11-01): max(R,G) < 50 flags ~11% of
// pixels, ~98% of them inside JRC occurrence > 0.
//
// GIBS daily tiles only hold that day's passes, so a single day shows cut swaths. The
// nisar://{mode}/{date}/{dirs}/{z}/{x}/{y} protocol mosaics the last MOSAIC_DAYS valid days
// (NISAR repeat cycle): newest day wins, older days fill transparent gaps. {dirs} is 'AD', 'A',
// 'D' or 'N' (none): with one direction, each day is clipped to that direction's CMR footprints.
export const NISAR_PROTOCOL = 'nisar'
export const MOSAIC_DAYS = 12
const WATER_THRESHOLD = 50
const WATER_RGB = [43, 140, 190]
const WATER_ALPHA = 153 // ~0.6
const COVER_RGB = [140, 150, 160] // #8c96a0
const COVER_ALPHA = 64 // ~0.25
const FEATHER = 2 // px box radius for alpha edges and day seams
const NISAR_GIBS = OVERLAYS.nisar.tiles

// Zoom crossfade: swath outlines when far, full mosaic when close.
export const NISAR_FADE_START = 6
export const NISAR_FADE_END = 8
// Footprint outline colors by orbit direction (muted so the map stays readable).
export const NISAR_ASC_COLOR = '#4a7fb5'
export const NISAR_DESC_COLOR = '#c0783a'
export const NISAR_OUTLINE_MAXZOOM = 9

let protocolAdded = false
const SIZE = 256

const inRanges = (iso: string) => NISAR_RANGES.some(([a, b]) => iso >= a && iso <= b)

// Valid NISAR days, newest first, within MOSAIC_DAYS ending at the (snapped) date.
export function mosaicDates(iso: string): string[] {
  const end = days(nisarDate(iso))
  const out: string[] = []
  for (let i = 0; i < MOSAIC_DAYS; i++) {
    const d = new Date((end - i) * 86400000).toISOString().slice(0, 10)
    if (inRanges(d)) out.push(d)
  }
  return out
}

async function emptyTile(): Promise<ArrayBuffer> {
  const c = new OffscreenCanvas(SIZE, SIZE)
  return (await c.convertToBlob({ type: 'image/png' })).arrayBuffer()
}

// Minimal PNG parse: IHDR fields plus PLTE and concatenated IDAT bytes.
interface Png {
  w: number
  h: number
  depth: number
  type: number // 2 RGB, 3 palette, 6 RGBA
  plte: Uint8Array | null
  idat: Uint8Array[]
}

function parsePng(b: Uint8Array): Png | null {
  if (b.length < 33 || b[0] !== 0x89 || b[1] !== 0x50) return null
  const dv = new DataView(b.buffer, b.byteOffset, b.byteLength)
  const png: Png = { w: dv.getUint32(16), h: dv.getUint32(20), depth: b[24], type: b[25], plte: null, idat: [] }
  for (let i = 8; i + 8 <= b.length; ) {
    const n = dv.getUint32(i)
    const t = String.fromCharCode(b[i + 4], b[i + 5], b[i + 6], b[i + 7])
    if (t === 'PLTE') png.plte = b.subarray(i + 8, i + 8 + n)
    else if (t === 'IDAT') png.idat.push(b.subarray(i + 8, i + 8 + n))
    else if (t === 'IEND') break
    i += 12 + n
  }
  return png
}

async function inflate(parts: Uint8Array[]): Promise<Uint8Array> {
  const s = new Blob(parts as BlobPart[]).stream().pipeThrough(new DecompressionStream('deflate'))
  return new Uint8Array(await new Response(s).arrayBuffer())
}

// Undoes PNG scanline filters (8-bit, bpp bytes per pixel); returns h*w*bpp bytes.
function unfilter(raw: Uint8Array, w: number, h: number, bpp: number): Uint8Array {
  const stride = w * bpp
  const out = new Uint8Array(h * stride)
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)]
    const src = y * (stride + 1) + 1
    const row = y * stride
    const prev = row - stride
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? out[row + x - bpp] : 0
      const up = y > 0 ? out[prev + x] : 0
      const c = x >= bpp && y > 0 ? out[prev + x - bpp] : 0
      let v = raw[src + x]
      if (f === 1) v += a
      else if (f === 2) v += up
      else if (f === 3) v += (a + up) >> 1
      else if (f === 4) {
        const p = a + up - c
        const pa = Math.abs(p - a)
        const pb = Math.abs(p - up)
        const pc = Math.abs(p - c)
        v += pa <= pb && pa <= pc ? a : pb <= pc ? up : c
      }
      out[row + x] = v
    }
  }
  return out
}

// GIBS NISAR tiles are 8-bit RGB with tRNS (0,0,0); genuinely empty tiles are the same, all
// black. The server is non-deterministic, though: the same URL sometimes comes back as
// - colour type 6 (RGBA) whose bytes are really the RGB image read with a 4-byte stride, so a
//   browser shows TV-snow; the first w*h*3 bytes are the true RGB, the rest is junk.
// - colour type 0 (grey) or 3 (palette, all-zero palette) holding only the first third of the
//   RGB bytes, which renders as grey stripes or a black tile and cannot be recovered;
// - HTTP 500.
// Returns RGBA for a recovered RGBA tile, 'native' for a normal RGB PNG, or 'retry'.
async function fixGibsPng(b: Uint8Array): Promise<Uint8ClampedArray | 'native' | 'retry'> {
  const png = parsePng(b)
  if (!png || png.depth !== 8 || b[28] !== 0 || png.w !== SIZE || png.h !== SIZE) return 'retry'
  if (png.type === 2) return 'native'
  if (png.type !== 6) return 'retry'
  const raw = await inflate(png.idat)
  if (raw.length !== SIZE * (SIZE * 4 + 1)) return 'retry'
  const bytes = unfilter(raw, SIZE, SIZE, 4)
  const out = new Uint8ClampedArray(SIZE * SIZE * 4)
  for (let i = 0; i < SIZE * SIZE; i++) {
    const r = bytes[i * 3]
    const g = bytes[i * 3 + 1]
    const bl = bytes[i * 3 + 2]
    out[i * 4] = r
    out[i * 4 + 1] = g
    out[i * 4 + 2] = bl
    out[i * 4 + 3] = r | g | bl ? 255 : 0 // same no-data key as the tRNS of normal tiles
  }
  return out
}

// Raw GIBS tile per URL, kept as served: compressed PNG Blob, RGBA for a recovered NISAR tile,
// or null when missing. Decoded on use, so the cache can hold neighbour zooms (see preloadAround).
// LRU bounded by bytes. FAIL marks a fetch that gave up (network error, 5xx, broken PNGs): it is
// not cached, unlike null, which means GIBS really has no tile there.
const FAIL = 'fail'
type Raw = Blob | Uint8ClampedArray | null | typeof FAIL
interface Entry {
  p: Promise<Raw>
  bytes: number
  pre: boolean // created by the preloader
}
const cache = new Map<string, Entry>()
const CACHE_BYTES = 150 * 1024 * 1024
const CACHE_MAX = 8000
let cacheBytes = 0

function evict() {
  for (const [k, e] of cache) {
    if (cacheBytes <= CACHE_BYTES && cache.size <= CACHE_MAX) break
    cache.delete(k)
    cacheBytes -= e.bytes
  }
}

// NISAR fetches go through a small pool: GIBS hands out more broken tiles under bursts.
const NISAR_POOL = 6
const NISAR_TRIES = 6
let nisarActive = 0
const nisarQueue: (() => void)[] = []

async function pooledFetch(url: string): Promise<Response> {
  if (nisarActive >= NISAR_POOL) await new Promise<void>((r) => nisarQueue.push(r))
  nisarActive++
  try {
    const res = await fetch(url)
    await res.clone().arrayBuffer() // hold the slot until the body is in
    return res
  } finally {
    nisarActive--
    nisarQueue.shift()?.()
  }
}

// NISAR tile body: refetches until GIBS returns a usable PNG; null after NISAR_TRIES (not cached).
async function nisarBlob(url: string): Promise<Blob | Uint8ClampedArray | null> {
  for (let i = 0; i < NISAR_TRIES; i++) {
    if (i) await new Promise((r) => setTimeout(r, 200 * i + Math.random() * 200))
    const res = await pooledFetch(url)
    if (res.status >= 400 && res.status < 500) return null // genuinely missing, no point retrying
    if (!res.ok) continue
    const blob = await res.blob()
    const fixed = await fixGibsPng(new Uint8Array(await blob.arrayBuffer()))
    if (fixed === 'native') return blob
    if (fixed !== 'retry') return fixed
  }
  throw new Error('gibs: no usable tile')
}

// Raw tile loads started for visible tiles and still running; the preloader waits on them.
let visiblePending = 0
const stats = { req: 0, hit: 0 } // visible raw requests / ones served by a preloaded entry

function loadRaw(url: string, fix: boolean, pre: boolean): Promise<Raw> {
  const hit = cache.get(url)
  if (hit) {
    cache.delete(url) // LRU: move to the newest end
    cache.set(url, hit)
    if (!pre) {
      stats.req++
      if (hit.pre) stats.hit++
    }
    return hit.p
  }
  if (!pre) {
    stats.req++
    visiblePending++
  }
  const e: Entry = { p: Promise.resolve(null), bytes: 0, pre }
  e.p = (async (): Promise<Raw> => {
    try {
      if (fix) return await nisarBlob(url)
      const res = await fetch(url)
      if (res.status >= 500) throw new Error(`gibs ${res.status}`)
      if (!res.ok || !(res.headers.get('content-type') ?? 'image/').startsWith('image/')) return null
      return await res.blob()
    } catch {
      if (cache.get(url) === e) cache.delete(url) // failures are retried on the next request
      return FAIL
    } finally {
      if (!pre) visiblePending--
    }
  })()
  void e.p.then((r) => {
    if (cache.get(url) !== e || !r || r === FAIL) return
    e.bytes = r instanceof Blob ? r.size : r.byteLength
    cacheBytes += e.bytes
    evict()
  })
  cache.set(url, e)
  evict()
  return e.p
}

// Decoded RGBA of a GIBS tile (decoded on every call; only compressed bytes are cached).
async function rawTile(url: string, fix = false): Promise<Uint8ClampedArray | null | typeof FAIL> {
  const r = await loadRaw(url, fix, false)
  if (!(r instanceof Blob)) return r
  try {
    const bmp = await createImageBitmap(r)
    const c = new OffscreenCanvas(SIZE, SIZE)
    const ctx = c.getContext('2d')!
    ctx.drawImage(bmp, 0, 0, SIZE, SIZE)
    bmp.close()
    return ctx.getImageData(0, 0, SIZE, SIZE).data
  } catch {
    return null
  }
}

// Tile preload (like chunk render distance in games): after the map settles, raw GIBS tiles are
// fetched into the cache in this order: a ring of PRELOAD_RING tiles around the view at the
// current zoom (panning), z-1 over the whole view (zooming out), z+1 over the central part of the
// view (zooming in). Visible tiles always go first: MapLibre loads them, and preload workers wait
// while any is pending. The PRELOAD_MAX budget is shared round-robin between layers, so with
// NISAR and DSWx on each gets half. The queue is dropped at the next map move.
const PRELOAD_POOL = 4
const PRELOAD_MAX = 300 // GETs per idle, all layers together
const PRELOAD_RING = 1 // tiles around the view at the current zoom (2 roughly doubles the cost)
const PRELOAD_INNER = 0.5 // share of the view area preloaded at z+1
let preloadGen = 0

export interface PreloadLayer {
  id: 'nisar' | 'dswx'
  date: string
  dirs?: string // NISAR 'AD' | 'A' | 'D' | 'N'
  fps?: NisarFootprint[] | null // NISAR: only days with a pass over the tile are preloaded
}

// Preload level: 0 = ring at the current zoom, 1 = z-1, 2 = z+1 (also the priority order).
export interface PreloadUrl {
  url: string
  fix: boolean
  lvl: 0 | 1 | 2
  layer: PreloadLayer['id']
}

// GIBS URLs to preload for a view (map zoom + lon/lat box [w, s, e, n]), capped at PRELOAD_MAX:
// per layer by level, nearest the view centre first; layers interleaved.
export function preloadUrls(
  zoom: number,
  [w, s, e, n]: [number, number, number, number],
  layers: PreloadLayer[],
): PreloadUrl[] {
  const zr = Math.round(zoom) // raster sources pick tiles at the rounded zoom
  const perLayer: PreloadUrl[][] = []
  for (const l of layers) {
    const nisar = l.id === 'nisar'
    if (nisar && l.dirs === 'N') continue
    const minz = nisar ? NISAR_FADE_START : 0
    const maxz = OVERLAYS[l.id].maxzoom
    const tpl = nisar ? NISAR_GIBS : DSWX_GIBS
    const dates = nisar ? mosaicDates(l.date) : dswxDates(l.date)
    const zc = Math.min(zr, maxz) // past maxzoom the source overzooms its last level
    const out: (PreloadUrl & { d: number })[] = []
    const levels: [0 | 1 | 2, number, number][] = [
      [0, zr, 1],
      [1, zr - 1, 1],
      [2, zr + 1, PRELOAD_INNER],
    ]
    for (const [lvl, zl, area] of levels) {
      const z = Math.min(zl, maxz)
      if ((lvl > 0 && z === zc) || z < minz) continue
      const k = Math.sqrt(area) // shrink the box around its centre (tile units) to the area share
      const cx = (lonX(w, z) + lonX(e, z)) / 2
      const cy = (latY(n, z) + latY(s, z)) / 2
      const hx = ((lonX(e, z) - lonX(w, z)) / 2) * k
      const hy = ((latY(s, z) - latY(n, z)) / 2) * k
      const last = 2 ** z - 1
      const c = (v: number) => Math.max(0, Math.min(last, Math.floor(v)))
      // Visible tile range; the ring level takes only the tiles around it.
      const x0 = c(cx - hx)
      const x1 = c(cx + hx - 1e-9)
      const y0 = c(cy - hy)
      const y1 = c(cy + hy - 1e-9)
      const r = lvl === 0 ? PRELOAD_RING : 0
      for (let x = Math.max(0, x0 - r); x <= Math.min(last, x1 + r); x++)
        for (let y = Math.max(0, y0 - r); y <= Math.min(last, y1 + r); y++) {
          if (lvl === 0 && x >= x0 && x <= x1 && y >= y0 && y <= y1) continue
          const d = (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2
          const [tw, ts, te, tn] = tileBounds(z, x, y)
          const fps = l.fps?.filter((f) => f.bbox[0] <= te && f.bbox[2] >= tw && f.bbox[1] <= tn && f.bbox[3] >= ts)
          for (const t of dates) {
            if (fps && !fps.some((f) => f.date === t)) continue // GIBS serves a blank tile there
            const url = tpl.replace('{time}', t).replace('{z}', String(z)).replace('{y}', String(y)).replace('{x}', String(x))
            out.push({ url, fix: nisar, lvl, layer: l.id, d })
          }
        }
    }
    out.sort((a, b) => a.lvl - b.lvl || a.d - b.d)
    perLayer.push(out.filter((u) => !cache.has(u.url)).map(({ url, fix, lvl, layer }) => ({ url, fix, lvl, layer })))
  }
  const res: PreloadUrl[] = []
  for (let i = 0; res.length < PRELOAD_MAX && perLayer.some((q) => i < q.length); i++)
    for (const q of perLayer) if (i < q.length && res.length < PRELOAD_MAX) res.push(q[i])
  return res
}

// Drops queued preloads; in-flight ones finish and stay cached.
export function cancelPreload() {
  preloadGen++
}

export async function preloadAround(zoom: number, view: [number, number, number, number], layers: PreloadLayer[]) {
  const gen = ++preloadGen
  // NISAR passes over the view plus a margin (z-1 tiles and the ring reach past it); a CMR
  // failure just means every day is preloaded.
  const [w, s, e, n] = view
  const mx = (e - w) / 2
  const my = (n - s) / 2
  const box: [number, number, number, number] = [Math.max(-180, w - mx), Math.max(-85, s - my), Math.min(180, e + mx), Math.min(85, n + my)]
  const withFps = await Promise.all(
    layers.map(async (l) =>
      l.id === 'nisar' && l.dirs !== 'N' ? { ...l, fps: await nisarFootprints(box, l.date).catch(() => null) } : l,
    ),
  )
  if (gen !== preloadGen) return
  const queue = preloadUrls(zoom, view, withFps)
  console.debug(
    `preload z${Math.round(zoom)}: ${queue.length} GET; cache ${cache.size} tiles, ${(cacheBytes / 1048576).toFixed(1)} MB; preload hits ${stats.hit}/${stats.req}`,
  )
  const worker = async () => {
    for (;;) {
      while (visiblePending > 0 && gen === preloadGen) await new Promise((r) => setTimeout(r, 100))
      const next = queue.shift()
      if (!next || gen !== preloadGen) return
      if (!cache.has(next.url)) await loadRaw(next.url, next.fix, true)
    }
  }
  for (let i = 0; i < PRELOAD_POOL; i++) void worker()
}

// Timeline prefetch: raw NISAR tiles of every pass day (and the days its mosaic draws on) over
// a box at the current zoom, nearest days to the shown one first, so stepping through the
// timeline hits the cache. Own generation counter: a new call (box, zoom, days) drops the queue.
const DAYS_POOL = 6
const DAYS_MAX_TILES = 64 // tiles per day at one zoom
const DAYS_MAX = 1500 // GETs per run
let daysGen = 0

export function cancelDaysPrefetch() {
  daysGen++
}

type Box = [number, number, number, number]

// Tile range of a box at zoom z.
function tileRange(z: number, [w, s, e, n]: Box): [number, number, number, number] {
  const last = 2 ** z - 1
  const c = (v: number) => Math.max(0, Math.min(last, Math.floor(v)))
  return [c(lonX(w, z)), c(lonX(e, z) - 1e-9), c(latY(n, z)), c(latY(s, z) - 1e-9)]
}

function unionBox(boxes: Box[]): Box {
  return [
    Math.min(...boxes.map((b) => b[0])),
    Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])),
    Math.max(...boxes.map((b) => b[3])),
  ]
}

// Fixed zoom for a target: the deepest NISAR zoom where the union of the boxes spans at most
// FRAME_MAX_SIDE tiles per side. Independent of the map view, so frames and cache stay stable.
export function targetZoom(boxes: Box[]): number {
  const u = unionBox(boxes)
  for (let z = OVERLAYS.nisar.maxzoom; z > NISAR_FADE_START; z--) {
    const [x0, x1, y0, y1] = tileRange(z, u)
    if (x1 - x0 + 1 <= FRAME_MAX_SIDE && y1 - y0 + 1 <= FRAME_MAX_SIDE) return z
  }
  return NISAR_FADE_START
}

// Tiles at zoom z that touch any of the boxes (bbox test), nearest to the union center first.
function targetTiles(boxes: Box[], z: number): [number, number][] {
  const keys = new Set<string>()
  const tiles: [number, number][] = []
  for (const b of boxes) {
    const [x0, x1, y0, y1] = tileRange(z, b)
    for (let x = x0; x <= x1; x++)
      for (let y = y0; y <= y1; y++)
        if (!keys.has(`${x}/${y}`)) {
          keys.add(`${x}/${y}`)
          tiles.push([x, y])
        }
  }
  const [ux0, ux1, uy0, uy1] = tileRange(z, unionBox(boxes))
  const cx = (ux0 + ux1 + 1) / 2
  const cy = (uy0 + uy1 + 1) / 2
  const d = (t: [number, number]) => (t[0] + 0.5 - cx) ** 2 + (t[1] + 0.5 - cy) ** 2
  return tiles.sort((a, b) => d(a) - d(b))
}

export async function prefetchDays(
  boxes: Box[],
  passDays: string[],
  current: string,
  onProgress: (p: { done: number; total: number; paused?: boolean } | null) => void,
) {
  const gen = ++daysGen
  let finish = () => {}
  daysReady = new Promise<void>((r) => (finish = r))
  if (!boxes.length || !passDays.length) return finish(), onProgress(null)
  const z = targetZoom(boxes)
  const tiles = targetTiles(boxes, z)
  tiles.length = Math.min(tiles.length, DAYS_MAX_TILES)
  const cur = days(current)
  const order = [...passDays].sort((a, b) => Math.abs(days(a) - cur) - Math.abs(days(b) - cur))
  const dates: string[] = []
  for (const d of order) for (const t of mosaicDates(d)) if (!dates.includes(t)) dates.push(t)
  // Already cached tiles count as done, so switching targets resumes instead of restarting.
  const all = new Set<string>()
  for (const t of dates)
    for (const [x, y] of tiles) all.add(NISAR_GIBS.replace('{time}', t).replace('{z}', String(z)).replace('{y}', String(y)).replace('{x}', String(x)))
  const urls = [...all].slice(0, DAYS_MAX)
  const queue = urls.filter((u) => !cache.has(u))
  const total = urls.length
  let done = total - queue.length
  if (!queue.length) return finish(), onProgress(null)
  onProgress({ done, total })
  const worker = async () => {
    for (;;) {
      // Yield to visible tiles, but never longer than DAYS_YIELD_MS: a hung visible fetch
      // would otherwise freeze the prefetch (and its counter) forever.
      const t0 = Date.now()
      let paused = false
      while (visiblePending > 0 && gen === daysGen && Date.now() - t0 < DAYS_YIELD_MS) {
        if (!paused) onProgress({ done: Math.min(done, total), total, paused: (paused = true) })
        await new Promise((r) => setTimeout(r, 100))
      }
      const url = queue.shift()
      if (!url || gen !== daysGen) return
      try {
        if (!cache.has(url)) await loadRaw(url, true, true)
      } catch {
        // counted as done anyway
      }
      if (gen !== daysGen) return
      done++
      onProgress(done >= total ? null : { done, total })
    }
  }
  void Promise.all(Array.from({ length: DAYS_POOL }, worker)).finally(finish)
}

// Resolves when the current prefetchDays run ends (finished or cancelled); buildFrames waits on it
// so both do not fight for the same tiles and the progress counter stays monotonic.
let daysReady: Promise<void> = Promise.resolve()
const DAYS_YIELD_MS = 3000

// Separable box blur of one channel, in place.
function boxBlur(a: Float32Array, w: number, h: number, r: number) {
  const t = new Float32Array(a.length)
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      let s = 0
      let n = 0
      for (let k = -r; k <= r; k++) {
        const xx = x + k
        if (xx >= 0 && xx < w) {
          s += a[y * w + xx]
          n++
        }
      }
      t[y * w + x] = s / n
    }
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      let s = 0
      let n = 0
      for (let k = -r; k <= r; k++) {
        const yy = y + k
        if (yy >= 0 && yy < h) {
          s += t[yy * w + x]
          n++
        }
      }
      a[y * w + x] = s / n
    }
}

// Orbit direction per granule comes from NASA CMR (keyless, CORS). Its GraphQL endpoint returns
// only the fields asked for (~250 B per granule; granules.json is ~20 KB). The direction is the
// A/D token of the granule name (NISAR_L2_PR_GCOV_<cycle>_<track>_<A|D>_<frame>_...), same as
// its ASCENDING_DESCENDING attribute. Footprints are frame polygons, keyed by UTC day like the
// GIBS daily tiles.
export type NisarDir = 'A' | 'D'
export interface NisarFootprint {
  id: string
  dir: NisarDir
  date: string // YYYY-MM-DD (UTC)
  rings: [number, number][][] // [lon, lat]
  bbox: [number, number, number, number] // w, s, e, n
}

const CMR_GRAPHQL = 'https://graphql.earthdata.nasa.gov/api'
// NISAR L2 GCOV collections at ASF (validated V1, provisional, beta).
const GCOV_COLLECTIONS = ['C3622241360-ASF', 'C2854338529-ASF', 'C3622214170-ASF']
const FOOT_CELL_Z = 4 // queries are cached per z4 tile (22.5 deg) and mosaic window
const FOOT_MAX_CELLS = 40 // larger views (zoomed far out) are not queried
const FOOT_PAGE = 2000
const footCache = new Map<string, Promise<NisarFootprint[]>>()

const lonX = (lon: number, z: number) => ((lon + 180) / 360) * 2 ** z
const latY = (lat: number, z: number) => {
  const r = (Math.max(-85.05, Math.min(85.05, lat)) * Math.PI) / 180
  return ((1 - Math.log(Math.tan(Math.PI / 4 + r / 2)) / Math.PI) / 2) * 2 ** z
}
const xLon = (x: number, z: number) => (x / 2 ** z) * 360 - 180
const yLat = (y: number, z: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 2 ** z))) * 180) / Math.PI

// Lon/lat box [w, s, e, n] of a web-mercator tile.
export function tileBounds(z: number, x: number, y: number): [number, number, number, number] {
  return [xLon(x, z), yLat(y + 1, z), xLon(x + 1, z), yLat(y, z)]
}

const GRANULES_QUERY = 'query($p:GranulesInput){granules(params:$p){cursor items{granuleUr timeStart polygons}}}'

async function footCell(cx: number, cy: number, dates: string[]): Promise<NisarFootprint[]> {
  const [w, s, e, n] = tileBounds(FOOT_CELL_Z, cx, cy)
  const out: NisarFootprint[] = []
  let cursor: string | undefined
  for (let page = 0; page < 5; page++) {
    const p = {
      collectionConceptIds: GCOV_COLLECTIONS,
      boundingBox: [`${w},${s},${e},${n}`],
      temporal: `${dates[dates.length - 1]}T00:00:00Z,${dates[0]}T23:59:59Z`,
      limit: FOOT_PAGE,
      ...(cursor ? { cursor } : {}),
    }
    const res = await fetch(CMR_GRAPHQL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: GRANULES_QUERY, variables: { p } }),
    })
    if (!res.ok) throw new Error(`cmr ${res.status}`)
    const g = (await res.json()).data?.granules
    if (!g) throw new Error('cmr: no data')
    const items = g.items as { granuleUr: string; timeStart: string; polygons: string[][] | null }[]
    for (const it of items) {
      const dir = /_GCOV_\d+_\d+_([AD])_/.exec(it.granuleUr)?.[1] as NisarDir | undefined
      if (!dir || !it.polygons) continue
      // CMR rings are "lat lon lat lon ..." strings; first ring of each polygon is the outer one.
      const rings = it.polygons.map((poly) => {
        const v = poly[0].trim().split(/\s+/).map(Number)
        const r: [number, number][] = []
        for (let i = 0; i + 1 < v.length; i += 2) r.push([v[i + 1], v[i]])
        return r
      })
      const lons = rings.flat().map((c) => c[0])
      const lats = rings.flat().map((c) => c[1])
      if (Math.max(...lons) - Math.min(...lons) > 180) continue // antimeridian crossers skipped
      out.push({
        id: it.granuleUr,
        dir,
        date: it.timeStart.slice(0, 10),
        rings,
        bbox: [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)],
      })
    }
    cursor = g.cursor
    if (!cursor || items.length < FOOT_PAGE) break
  }
  return out
}

// NISAR GCOV footprints (deduped) touching a lon/lat box [w, s, e, n] within the mosaic window
// ending at date. Rejects when the box needs more than FOOT_MAX_CELLS cell queries.
export async function nisarFootprints(
  [w, s, e, n]: [number, number, number, number],
  date: string,
): Promise<NisarFootprint[]> {
  const dates = mosaicDates(date)
  if (!dates.length) return []
  const z = FOOT_CELL_Z
  const last = 2 ** z - 1
  const x0 = Math.max(0, Math.floor(lonX(w, z)))
  const x1 = Math.min(last, Math.ceil(lonX(e, z)) - 1)
  const y0 = Math.max(0, Math.floor(latY(n, z)))
  const y1 = Math.min(last, Math.ceil(latY(s, z)) - 1)
  if ((x1 - x0 + 1) * (y1 - y0 + 1) > FOOT_MAX_CELLS) throw new Error('nisar footprints: view too large')
  const cells: Promise<NisarFootprint[]>[] = []
  for (let cx = x0; cx <= x1; cx++)
    for (let cy = y0; cy <= y1; cy++) {
      const key = `${cx}/${cy}/${dates[0]}`
      let p = footCache.get(key)
      if (!p) {
        p = footCell(cx, cy, dates)
        p.catch(() => footCache.delete(key)) // failures are retried on the next request
        footCache.set(key, p)
      }
      cells.push(p)
    }
  const seen = new Set<string>()
  return (await Promise.all(cells)).flat().filter((f) => !seen.has(f.id) && !!seen.add(f.id))
}

// Rasterizes footprint rings into a tile-sized coverage mask (1 = inside).
function footMask(fps: NisarFootprint[], z: number, x: number, y: number): Uint8Array {
  const c = new OffscreenCanvas(SIZE, SIZE)
  const ctx = c.getContext('2d')!
  ctx.fillStyle = '#000'
  for (const f of fps)
    for (const r of f.rings) {
      ctx.beginPath()
      r.forEach(([lon, lat], i) => {
        const px = (lonX(lon, z) - x) * SIZE
        const py = (latY(lat, z) - y) * SIZE
        if (i) ctx.lineTo(px, py)
        else ctx.moveTo(px, py)
      })
      ctx.closePath()
      ctx.fill()
    }
  const a = ctx.getImageData(0, 0, SIZE, SIZE).data
  const m = new Uint8Array(SIZE * SIZE)
  for (let i = 0; i < m.length; i++) m[i] = a[i * 4 + 3] >= 128 ? 1 : 0
  return m
}

// Keeps one day's pixels from the wanted direction. The day is dropped when only other-direction
// passes touch the tile; when both directions do, pixels inside an other-direction footprint and
// outside every wanted one are cleared (footprint edges are approximate, so the rest is kept).
// A day with pixels but no footprint at all (granule missing from CMR) is kept unfiltered.
function clipDay(
  t: Uint8ClampedArray,
  fps: NisarFootprint[],
  date: string,
  want: NisarDir,
  z: number,
  x: number,
  y: number,
): Uint8ClampedArray | null {
  const [w, s, e, n] = tileBounds(z, x, y)
  const hit = fps.filter((f) => f.date === date && f.bbox[0] <= e && f.bbox[2] >= w && f.bbox[1] <= n && f.bbox[3] >= s)
  const wanted = hit.filter((f) => f.dir === want)
  const other = hit.filter((f) => f.dir !== want)
  if (!hit.length) return t
  if (!wanted.length) return null
  if (!other.length) return t
  const mw = footMask(wanted, z, x, y)
  const mo = footMask(other, z, x, y)
  const out = t.slice()
  for (let i = 0; i < mw.length; i++) if (mo[i] && !mw[i]) out[i * 4 + 3] = 0
  return out
}

// Tiles built with failed GIBS/CMR fetches, per overlay ("z/x/y"), waiting for a retry at the
// next map idle (see takeFailedTiles). A tile is retried at most RETRY_MAX times.
const RETRY_MAX = 3
const failed: Record<'nisar' | 'dswx', Set<string>> = { nisar: new Set(), dswx: new Set() }
const retries = new Map<string, number>()

function noteFailed(id: 'nisar' | 'dswx', z: string, x: string, y: string) {
  const k = `${z}/${x}/${y}`
  if (failed[id].has(k)) return // already queued for this attempt
  const n = retries.get(`${id}/${k}`) ?? 0
  if (n >= RETRY_MAX) return
  retries.set(`${id}/${k}`, n + 1)
  failed[id].add(k)
}

// Drains the tiles waiting for a retry, as {z, x, y} per overlay id.
export function takeFailedTiles(): { id: 'nisar' | 'dswx'; tiles: { z: number; x: number; y: number }[] }[] {
  const out: { id: 'nisar' | 'dswx'; tiles: { z: number; x: number; y: number }[] }[] = []
  for (const id of ['nisar', 'dswx'] as const) {
    if (!failed[id].size) continue
    out.push({
      id,
      tiles: [...failed[id]].map((k) => {
        const [z, x, y] = k.split('/').map(Number)
        return { z, x, y }
      }),
    })
    failed[id].clear()
  }
  return out
}

// Turns FAIL day tiles into null. Throws when something failed and nothing usable came back, so
// MapLibre marks the tile errored instead of keeping a blank one forever; a partial result is
// kept but queued for a retry.
function settleDays(
  id: 'nisar' | 'dswx',
  tiles: (Uint8ClampedArray | null | typeof FAIL)[],
  z: string,
  x: string,
  y: string,
): (Uint8ClampedArray | null)[] {
  const bad = tiles.filter((t) => t === FAIL).length
  const ok = tiles.map((t) => (t === FAIL ? null : t))
  if (!bad) return ok
  noteFailed(id, z, x, y)
  if (!ok.some((t) => t)) throw new Error(`${id}: ${bad} day tiles failed`)
  return ok
}

async function mosaicTile(mode: NisarMode, date: string, dirs: string, z: string, x: string, y: string): Promise<ArrayBuffer> {
  if (dirs === 'N') return emptyTile()
  const dates = mosaicDates(date)
  const [days, fps] = await Promise.all([
    Promise.all(
      dates.map((d) => rawTile(NISAR_GIBS.replace('{time}', d).replace('{z}', z).replace('{y}', y).replace('{x}', x), true)),
    ),
    dirs === 'A' || dirs === 'D'
      ? nisarFootprints(tileBounds(+z, +x, +y), date).catch(() => {
          noteFailed('nisar', z, x, y) // shown unfiltered for now
          return null
        })
      : null,
  ])
  const tiles = settleDays('nisar', days, z, x, y)
  // One direction: clip each day to that direction's footprints (CMR failure = unfiltered).
  if (fps) tiles.forEach((t, i) => (tiles[i] = t && clipDay(t, fps, dates[i], dirs as NisarDir, +z, +x, +y)))
  const n = SIZE * SIZE
  const out = new Uint8ClampedArray(n * 4)
  const src = new Int8Array(n).fill(-1) // index of the day that filled each pixel
  tiles.forEach((t, di) => {
    if (!t) return
    for (let i = 0; i < n; i++) {
      if (src[i] >= 0 || t[i * 4 + 3] === 0) continue
      src[i] = di
      out.set(t.subarray(i * 4, i * 4 + 4), i * 4)
    }
  })
  if (!src.some((v) => v >= 0)) return emptyTile()

  const cover = new Float32Array(n)
  for (let i = 0; i < n; i++) cover[i] = src[i] >= 0 ? 1 : 0
  boxBlur(cover, SIZE, SIZE, FEATHER)

  if (mode === 'water') {
    const dark = new Uint8Array(n)
    for (let i = 0; i < n; i++) dark[i] = src[i] >= 0 && Math.max(out[i * 4], out[i * 4 + 1]) < WATER_THRESHOLD ? 1 : 0
    const water = new Float32Array(n)
    for (let yy = 0; yy < SIZE; yy++)
      for (let xx = 0; xx < SIZE; xx++) {
        let c = 0
        for (let dy = -1; dy <= 1; dy++)
          for (let dx = -1; dx <= 1; dx++) {
            const a = yy + dy
            const b = xx + dx
            if (a >= 0 && a < SIZE && b >= 0 && b < SIZE) c += dark[a * SIZE + b]
          }
        const i = yy * SIZE + xx
        water[i] = src[i] >= 0 && c >= 5 ? 1 : 0 // 3x3 majority cuts speckle
      }
    boxBlur(water, SIZE, SIZE, 1)
    for (let i = 0; i < n; i++) {
      const aW = (water[i] * WATER_ALPHA) / 255
      const aC = (cover[i] * COVER_ALPHA) / 255
      const a = aW + aC * (1 - aW) // water drawn over the coverage tint
      const k = i * 4
      for (let c = 0; c < 3; c++) out[k + c] = a > 0 ? (WATER_RGB[c] * aW + COVER_RGB[c] * aC * (1 - aW)) / a : 0
      out[k + 3] = a * 255
    }
  } else {
    // Soften seams between days: average RGB around pixels next to another day's pixels.
    const r = FEATHER
    const copy = out.slice()
    for (let yy = 0; yy < SIZE; yy++)
      for (let xx = 0; xx < SIZE; xx++) {
        const i = yy * SIZE + xx
        if (src[i] < 0) continue
        let seam = false
        for (let d = -r; d <= r && !seam; d++) {
          const j1 = xx + d >= 0 && xx + d < SIZE ? src[i + d] : src[i]
          const j2 = yy + d >= 0 && yy + d < SIZE ? src[i + d * SIZE] : src[i]
          if ((j1 >= 0 && j1 !== src[i]) || (j2 >= 0 && j2 !== src[i])) seam = true
        }
        if (!seam) continue
        const s = [0, 0, 0]
        let m = 0
        for (let dy = -r; dy <= r; dy++)
          for (let dx = -r; dx <= r; dx++) {
            const a = yy + dy
            const b = xx + dx
            if (a < 0 || a >= SIZE || b < 0 || b >= SIZE) continue
            const j = a * SIZE + b
            if (src[j] < 0) continue
            for (let c = 0; c < 3; c++) s[c] += copy[j * 4 + c]
            m++
          }
        for (let c = 0; c < 3; c++) out[i * 4 + c] = s[c] / m
      }
    for (let i = 0; i < n; i++) out[i * 4 + 3] = src[i] >= 0 ? cover[i] * 255 : 0
  }
  const c = new OffscreenCanvas(SIZE, SIZE)
  c.getContext('2d')!.putImageData(new ImageData(out, SIZE, SIZE), 0, 0)
  return (await c.convertToBlob({ type: 'image/png' })).arrayBuffer()
}

// OPERA DSWx-S1 (GIBS colormap OPERA_Dynamic_Surface_Water_Extent_S1): fill (255) is already
// transparent; HAND-masked (200,200,200) and layover/shadow (128,128,128) carry no water info,
// so they only show where no day in the window has a real class (not water/water/inundated veg).
export const DSWX_PROTOCOL = 'dswx'
const DSWX_GIBS = OVERLAYS.dswx.tiles
const DSWX_START = '2023-12-15'

// Last MOSAIC_DAYS calendar days ending at iso (DSWx is daily and continuous since DSWX_START).
export function dswxDates(iso: string): string[] {
  const end = days(iso)
  const out: string[] = []
  for (let i = 0; i < MOSAIC_DAYS; i++) {
    const d = new Date((end - i) * 86400000).toISOString().slice(0, 10)
    if (d >= DSWX_START) out.push(d)
  }
  return out
}

// Exact class colors from the GIBS colormap (not water, open water, inundated veg); any other
// RGB is a compression/edge artifact in a GIBS tile and is treated as empty.
const DSWX_REAL = new Set([0xffffff, 0x0000ff, 0x00ff00])
const DSWX_MASKED = new Set([0xc8c8c8, 0x808080]) // HAND masked, layover/shadow masked

// 0 = empty or invalid color, 1 = masked (weak), 2 = real class.
function dswxRank(t: Uint8ClampedArray, k: number): number {
  if (t[k + 3] !== 255) return 0
  const rgb = (t[k] << 16) | (t[k + 1] << 8) | t[k + 2]
  if (DSWX_REAL.has(rgb)) return 2
  if (DSWX_MASKED.has(rgb)) return 1
  return 0
}

// Newest real class wins, masked pixels only fill leftovers; class colors are copied unchanged
// and only alpha is feathered at coverage edges.
async function dswxTile(date: string, z: string, x: string, y: string): Promise<ArrayBuffer> {
  const tiles = settleDays(
    'dswx',
    await Promise.all(
      dswxDates(date).map((d) => rawTile(DSWX_GIBS.replace('{time}', d).replace('{z}', z).replace('{y}', y).replace('{x}', x))),
    ),
    z,
    x,
    y,
  )
  const n = SIZE * SIZE
  const out = new Uint8ClampedArray(n * 4)
  const rank = new Uint8Array(n)
  for (const want of [2, 1])
    for (const t of tiles) {
      if (!t) continue
      for (let i = 0; i < n; i++) {
        if (rank[i] || dswxRank(t, i * 4) !== want) continue
        rank[i] = want
        out.set(t.subarray(i * 4, i * 4 + 3), i * 4)
      }
    }
  if (!rank.some((v) => v)) return emptyTile()
  const cover = new Float32Array(n)
  for (let i = 0; i < n; i++) cover[i] = rank[i] ? 1 : 0
  boxBlur(cover, SIZE, SIZE, FEATHER)
  for (let i = 0; i < n; i++) out[i * 4 + 3] = rank[i] ? cover[i] * 255 : 0
  const c = new OffscreenCanvas(SIZE, SIZE)
  c.getContext('2d')!.putImageData(new ImageData(out, SIZE, SIZE), 0, 0)
  return (await c.convertToBlob({ type: 'image/png' })).arrayBuffer()
}

// Registers nisar://{mode}/{date}/{dirs}/{z}/{x}/{y} and dswx://{date}/{z}/{x}/{y} once. Errors
// propagate, so MapLibre marks the tile errored (a blank tile would never be refetched).
export function registerNisarProtocol(add: (name: string, fn: (p: { url: string }, ac: AbortController) => Promise<{ data: ArrayBuffer }>) => void) {
  if (protocolAdded) return
  protocolAdded = true
  add(NISAR_PROTOCOL, async (params, ac) => {
    const [mode, date, dirs, z, x, y] = params.url.replace(`${NISAR_PROTOCOL}://`, '').split('/')
    try {
      return { data: await mosaicTile(mode === 'color' ? mode : 'water', date, dirs, z, x, y) }
    } catch (e) {
      if (!ac.signal.aborted) noteFailed('nisar', z, x, y)
      throw e
    }
  })
  add(DSWX_PROTOCOL, async (params, ac) => {
    const [date, z, x, y] = params.url.replace(`${DSWX_PROTOCOL}://`, '').split('/')
    try {
      return { data: await dswxTile(date, z, x, y) }
    } catch (e) {
      if (!ac.signal.aborted) noteFailed('dswx', z, x, y)
      throw e
    }
  })
}

// Animation frames: each pass day pre-rendered as one image over a box at a fixed zoom, so the
// map swaps a single image per step (no tile reload, no flicker). Built from the same mosaics as
// the tile layer, so the raw tiles come from the cache filled by prefetchDays.
export interface DayFrame {
  url: string // object URL of the PNG
  coordinates: [[number, number], [number, number], [number, number], [number, number]]
}
const FRAME_MAX_SIDE = 8 // tiles per side
let framesGen = 0

export function cancelFrames() {
  framesGen++
}

async function composeDay(mode: NisarMode, date: string, dirs: string, z: number, x0: number, x1: number, y0: number, y1: number, gen: number): Promise<DayFrame | null> {
  const c = new OffscreenCanvas((x1 - x0 + 1) * SIZE, (y1 - y0 + 1) * SIZE)
  const g = c.getContext('2d')!
  let any = false
  for (let x = x0; x <= x1; x++)
    for (let y = y0; y <= y1; y++) {
      if (gen !== framesGen) return null
      try {
        const buf = await mosaicTile(mode, date, dirs, String(z), String(x), String(y))
        const bmp = await createImageBitmap(new Blob([buf], { type: 'image/png' }))
        g.drawImage(bmp, (x - x0) * SIZE, (y - y0) * SIZE)
        bmp.close()
        any = true
      } catch {
        // missing tile: left transparent
      }
    }
  if (!any) return null
  const [w, , , n] = tileBounds(z, x0, y0)
  const [, s, e] = tileBounds(z, x1, y1)
  const url = URL.createObjectURL(await c.convertToBlob({ type: 'image/png' }))
  return { url, coordinates: [[w, n], [e, n], [e, s], [w, s]] }
}

// Builds a frame per pass day (nearest to current first); onFrame fires as each one is ready.
export async function buildFrames(
  boxes: Box[],
  passDays: string[],
  current: string,
  mode: NisarMode,
  dirs: string,
  onFrame: (day: string, f: DayFrame | null, done: number, total: number) => void,
) {
  const gen = ++framesGen
  if (!boxes.length || !passDays.length || dirs === 'N') return
  const z = targetZoom(boxes)
  let [x0, x1, y0, y1] = tileRange(z, unionBox(boxes))
  const clamp = (a: number, b: number): [number, number] => {
    if (b - a + 1 <= FRAME_MAX_SIDE) return [a, b]
    const m = Math.floor((a + b) / 2) - FRAME_MAX_SIDE / 2 + 1
    return [m, m + FRAME_MAX_SIDE - 1]
  }
  ;[x0, x1] = clamp(x0, x1)
  ;[y0, y1] = clamp(y0, y1)
  const cur = days(current)
  const order = [...passDays].sort((a, b) => Math.abs(days(a) - cur) - Math.abs(days(b) - cur))
  let done = 0
  await Promise.race([daysReady, new Promise((r) => setTimeout(r, 60000))])
  if (gen !== framesGen) return
  for (const d of order) {
    const f = await composeDay(mode, nisarDate(d), dirs, z, x0, x1, y0, y1, gen)
    if (gen !== framesGen) {
      if (f) URL.revokeObjectURL(f.url)
      return
    }
    onFrame(d, f, ++done, order.length)
  }
}
