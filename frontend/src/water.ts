import { useRef, useState } from 'react'
import type { BBox } from './nominatim'

// U-Net water detection on the latest NISAR GCOV HH scene (POST /api/water).
export interface WaterResult {
  id: string
  scene_id: string
  datetime: string
  bounds: [number, number, number, number] // west, south, east, north (WGS84)
  threshold: number
  water_fraction: number
  valid_fraction: number
  png_url: string
  cached: boolean
  timings: Record<string, number>
}

export type WaterState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; result: WaterResult }

export interface WaterController {
  state: WaterState
  opacity: number // 0-100
  visible: boolean
  run: (bbox: BBox) => void
  setOpacity: (v: number) => void
  setVisible: (v: boolean) => void
  clear: () => void
}

export function useWater(): WaterController {
  const [state, setState] = useState<WaterState>({ status: 'idle' })
  const [opacity, setOpacity] = useState(85)
  const [visible, setVisible] = useState(true)
  // Latest request id; stale responses (after a newer run or clear) are dropped.
  const seq = useRef(0)
  const run = (bbox: BBox) => {
    const id = ++seq.current
    setState({ status: 'loading' })
    fetch('/api/water', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bbox }),
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}))
        if (id !== seq.current) return
        if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`)
        setState({ status: 'ready', result: body as WaterResult })
        setVisible(true)
      })
      .catch((e: Error) => {
        if (id === seq.current) setState({ status: 'error', message: e.message })
      })
  }
  return { state, opacity, visible, run, setOpacity, setVisible, clear: () => {
      seq.current++
      setState({ status: 'idle' })
    },
  }
}

// Corner order for a MapLibre image source: top-left, top-right, bottom-right, bottom-left.
export const waterCorners = ([w, s, e, n]: WaterResult['bounds']): [
  [number, number],
  [number, number],
  [number, number],
  [number, number],
] => [
  [w, n],
  [e, n],
  [e, s],
  [w, s],
]
