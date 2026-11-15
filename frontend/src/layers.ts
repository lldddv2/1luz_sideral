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
}

// 'water' = thresholded low-backscatter mask; 'color' = softened false-color preview.
export type NisarMode = 'water' | 'color'

const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best'

export const OVERLAYS: Record<OverlayId, Overlay> = {
  dswx: {
    id: 'dswx',
    label: 'OPERA DSWx-S1',
    hint: 'Agua superficial (Sentinel-1, banda C); mosaico de 12 días, el pase más reciente manda',
    tiles: `${GIBS}/OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1/default/{time}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png`,
    maxzoom: 12,
    attribution: 'OPERA DSWx-S1 · NASA GIBS',
    needsDate: true,
  },
  nisar: {
    id: 'nisar',
    label: 'NISAR GCOV (vista previa)',
    hint: 'Retrodispersión banda L de GIBS; usa la fecha válida más cercana',
    tiles: `${GIBS}/NISAR_L2_Geocoded_Polarimetric_Covariance/default/{time}/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png`,
    maxzoom: 13,
    attribution: 'NISAR GCOV · NASA-ISRO · NASA GIBS',
    needsDate: true,
  },
  jrc: {
    id: 'jrc',
    label: 'JRC agua histórica',
    hint: 'Frecuencia de agua 1984–2021; separa agua permanente de inundación',
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
  nisar: { on: false, opacity: 80, date: '2026-11-01', mode: 'color', outline: true },
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
// nisar://{mode}/{date}/{z}/{x}/{y} protocol mosaics the last MOSAIC_DAYS valid days
// (NISAR repeat cycle): newest day wins, older days fill transparent gaps.
export const NISAR_PROTOCOL = 'nisar'
export const MOSAIC_DAYS = 12
const WATER_THRESHOLD = 50
const WATER_RGB = [43, 140, 190]
const WATER_ALPHA = 153 // ~0.6
const COVER_RGB = [140, 150, 160] // #8c96a0
const COVER_ALPHA = 64 // ~0.25
const FEATHER = 2 // px box radius for alpha edges and day seams
const NISAR_GIBS = OVERLAYS.nisar.tiles
const OUTLINE_RGB = [0, 0, 0] // black swath outline
const OUTLINE_ALPHA = 110 // ~0.43: visible orbit trace without dominating the map

// Zoom crossfade: swath outlines when far, full mosaic when close.
export const NISAR_FADE_START = 6
export const NISAR_FADE_END = 8
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

// Raw RGBA per GIBS tile URL; null = missing/failed. Bounded FIFO cache.
const cache = new Map<string, Promise<Uint8ClampedArray | null>>()
const CACHE_MAX = 500

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

function rawTile(url: string, fix = false): Promise<Uint8ClampedArray | null> {
  const hit = cache.get(url)
  if (hit) return hit
  const p = (async () => {
    try {
      let blob: Blob
      if (fix) {
        const b = await nisarBlob(url)
        if (!(b instanceof Blob)) return b
        blob = b
      } else {
        const res = await fetch(url)
        if (!res.ok || !(res.headers.get('content-type') ?? 'image/').startsWith('image/')) return null
        blob = await res.blob()
      }
      const bmp = await createImageBitmap(blob)
      const c = new OffscreenCanvas(SIZE, SIZE)
      const ctx = c.getContext('2d')!
      ctx.drawImage(bmp, 0, 0, SIZE, SIZE)
      bmp.close()
      return ctx.getImageData(0, 0, SIZE, SIZE).data
    } catch {
      cache.delete(url)
      return null
    }
  })()
  cache.set(url, p)
  if (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value!)
  return p
}

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

// Draws each day's swath boundary (data/no-data edge, ~2px) in one color; inside is transparent.
function outlineTile(tiles: (Uint8ClampedArray | null)[]): Uint8ClampedArray<ArrayBuffer> | null {
  const n = SIZE * SIZE
  const edge = new Uint8Array(n)
  let any = false
  for (const t of tiles) {
    if (!t) continue
    for (let y = 0; y < SIZE; y++)
      for (let x = 0; x < SIZE; x++) {
        const i = y * SIZE + x
        if (t[i * 4 + 3] === 0) continue
        any = true
        // Covered pixel with an uncovered neighbor (tile borders are not edges).
        for (let d = 0; d < 4; d++) {
          const xx = x + (d === 0 ? -1 : d === 1 ? 1 : 0)
          const yy = y + (d === 2 ? -1 : d === 3 ? 1 : 0)
          if (xx < 0 || yy < 0 || xx >= SIZE || yy >= SIZE) continue
          if (t[(yy * SIZE + xx) * 4 + 3] === 0) {
            edge[i] = 1
            edge[yy * SIZE + xx] = 1 // second pixel outside makes the line ~2px
            break
          }
        }
      }
  }
  if (!any) return null
  const out = new Uint8ClampedArray(n * 4)
  for (let i = 0; i < n; i++)
    if (edge[i]) {
      out.set(OUTLINE_RGB, i * 4)
      out[i * 4 + 3] = OUTLINE_ALPHA
    }
  return out
}

async function mosaicTile(mode: NisarMode | 'outline', date: string, z: string, x: string, y: string): Promise<ArrayBuffer> {
  const dates = mosaicDates(date)
  const tiles = await Promise.all(
    dates.map((d) => rawTile(NISAR_GIBS.replace('{time}', d).replace('{z}', z).replace('{y}', y).replace('{x}', x), true)),
  )
  if (mode === 'outline') {
    const o = outlineTile(tiles)
    if (!o) return emptyTile()
    const c = new OffscreenCanvas(SIZE, SIZE)
    c.getContext('2d')!.putImageData(new ImageData(o, SIZE, SIZE), 0, 0)
    return (await c.convertToBlob({ type: 'image/png' })).arrayBuffer()
  }
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
  const tiles = await Promise.all(
    dswxDates(date).map((d) => rawTile(DSWX_GIBS.replace('{time}', d).replace('{z}', z).replace('{y}', y).replace('{x}', x))),
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

// Registers nisar://{mode}/{date}/{z}/{x}/{y} once; errors resolve to an empty tile.
export function registerNisarProtocol(add: (name: string, fn: (p: { url: string }, ac: AbortController) => Promise<{ data: ArrayBuffer }>) => void) {
  if (protocolAdded) return
  protocolAdded = true
  add(NISAR_PROTOCOL, async (params, ac) => {
    const [mode, date, z, x, y] = params.url.replace(`${NISAR_PROTOCOL}://`, '').split('/')
    try {
      return { data: await mosaicTile(mode === 'color' || mode === 'outline' ? mode : 'water', date, z, x, y) }
    } catch (e) {
      if (ac.signal.aborted) throw e
      return { data: await emptyTile() }
    }
  })
  add(DSWX_PROTOCOL, async (params, ac) => {
    const [date, z, x, y] = params.url.replace(`${DSWX_PROTOCOL}://`, '').split('/')
    try {
      return { data: await dswxTile(date, z, x, y) }
    } catch (e) {
      if (ac.signal.aborted) throw e
      return { data: await emptyTile() }
    }
  })
}
