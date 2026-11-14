// Geometry helpers for editing shapes. Rotation and rectangle resizing are computed in
// Web Mercator meters, so right angles and rotations look correct on the map.
import type { LngLat } from './types'

export type XY = [number, number]

const R = 6378137
const RAD = Math.PI / 180
const MAX_LAT = 85.051129

export const toMerc = ([lon, lat]: LngLat): XY => {
  const l = Math.max(-MAX_LAT, Math.min(MAX_LAT, lat))
  return [R * lon * RAD, R * Math.log(Math.tan(Math.PI / 4 + (l * RAD) / 2))]
}

export const fromMerc = ([x, y]: XY): LngLat => [x / R / RAD, (2 * Math.atan(Math.exp(y / R)) - Math.PI / 2) / RAD]

const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]]
const add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const scale = (a: XY, k: number): XY => [a[0] * k, a[1] * k]
const dot = (a: XY, b: XY) => a[0] * b[0] + a[1] * b[1]

// Rectangle rings are c0..c3 with edges 0-1 / 3-2 along axis u and edges 1-2 / 0-3 along axis v.
const sideU = (i: number) => i === 1 || i === 2
const sideV = (i: number) => i === 2 || i === 3

const rectAxes = (c: XY[]): [XY, XY] => {
  const e = sub(c[1], c[0])
  const len = Math.hypot(e[0], e[1])
  const u: XY = len > 0 ? scale(e, 1 / len) : [1, 0]
  return [u, [-u[1], u[0]]]
}

// Drags corner `index` to `p`, keeping the opposite corner fixed and the rectangle's orientation.
export function resizeCorner(origin: LngLat[], index: number, p: LngLat): LngLat[] {
  const c = origin.map(toMerc)
  const k = (index + 2) % 4
  const [u, v] = rectAxes(c)
  const d = sub(toMerc(p), c[k])
  const du = scale(u, dot(d, u))
  const dv = scale(v, dot(d, v))
  return c.map((_, j) => {
    let q = c[k]
    if (sideU(j) !== sideU(k)) q = add(q, du)
    if (sideV(j) !== sideV(k)) q = add(q, dv)
    return fromMerc(q)
  })
}

// Moves edge `index` (corners index and index+1) along its normal; the opposite edge stays fixed.
export function resizeEdge(origin: LngLat[], index: number, start: LngLat, p: LngLat): LngLat[] {
  const c = origin.map(toMerc)
  const [u, v] = rectAxes(c)
  const n = index % 2 === 0 ? v : u
  const delta = scale(n, dot(sub(toMerc(p), toMerc(start)), n))
  return c.map((q, j) => fromMerc(j === index || j === (index + 1) % 4 ? add(q, delta) : q))
}

export const centroid = (coords: LngLat[]): XY => {
  const c = coords.map(toMerc)
  return scale(
    c.reduce((acc, q) => add(acc, q), [0, 0] as XY),
    1 / c.length,
  )
}

export const angleFrom = (center: XY, p: LngLat) => {
  const d = sub(toMerc(p), center)
  return Math.atan2(d[1], d[0])
}

export function rotate(origin: LngLat[], center: XY, angle: number): LngLat[] {
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  return origin.map((p) => {
    const d = sub(toMerc(p), center)
    return fromMerc(add(center, [d[0] * cos - d[1] * sin, d[0] * sin + d[1] * cos]))
  })
}

// Rotation handle, anchored to a rectangle side midpoint or a polygon vertex and pointing outward
// from the centroid, so it stays attached and turns with the shape. Returns [anchor, handle, anchorIndex].
// Without `index` the highest anchor is used; pass the index during a rotation drag so it does not jump.
export function rotateHandle(
  coords: LngLat[],
  kind: 'polygon' | 'rectangle',
  index?: number,
): [LngLat, LngLat, number] {
  const c = coords.map(toMerc)
  const anchors = kind === 'rectangle' ? c.map((q, i) => scale(add(q, c[(i + 1) % c.length]), 0.5)) : c
  const i = index ?? anchors.reduce((best, q, j) => (q[1] > anchors[best][1] ? j : best), 0)
  const anchor = anchors[i]
  const center = scale(
    c.reduce((acc, q) => add(acc, q), [0, 0] as XY),
    1 / c.length,
  )
  const d = sub(anchor, center)
  const len = Math.hypot(d[0], d[1])
  const dir: XY = len > 0 ? scale(d, 1 / len) : [0, 1]
  const xs = c.map((q) => q[0])
  const ys = c.map((q) => q[1])
  const offset = 0.2 * Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys))
  return [fromMerc(anchor), fromMerc(add(anchor, scale(dir, offset))), i]
}
