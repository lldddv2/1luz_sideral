import { useEffect, useRef, useState } from 'react'
import type { BBox } from './nominatim'

// External model connection (see /api/models): the browser holds a session token,
// a local Python client pulls jobs with it, and results arrive over SSE.
export interface WaterResult {
  job_id: string
  scene_id?: string
  datetime?: string
  bounds: [number, number, number, number] // west, south, east, north (WGS84)
  output?: ModelOutput
  label?: string
  units?: string
  stats?: { min?: number; max?: number; mean?: number; fraction?: number }
  legend?: { min: number; max: number } | { classes: { value: number; color: string }[] }
  png_url: string
}

export type ModelOutput = 'probability' | 'continuous' | 'classes'

export type JobState = 'queued' | 'running' | 'done' | 'error'

export type WaterState =
  | { status: 'idle' }
  | { status: 'job'; job_id: string; state: Exclude<JobState, 'done' | 'error'> }
  | { status: 'error'; message: string }
  | { status: 'ready'; result: WaterResult }

export interface ModelStatus {
  connected: boolean
  name: string | null
  output?: ModelOutput
  label?: string
  units?: string
  pols?: string[]
}

export interface WaterController {
  token: string | null
  tokenError: string | null
  model: ModelStatus
  state: WaterState
  opacity: number // 0-100
  visible: boolean
  regenerate: () => void
  run: (bbox: BBox) => void
  runBuiltin: (bbox: BBox) => void // built-in water U-Net (POST /api/water)
  setOpacity: (v: number) => void
  setVisible: (v: boolean) => void
  clear: () => void
}

const TOKEN_KEY = 'luzsi.modelToken'

const readToken = (): string | null => {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}
const storeToken = (t: string | null) => {
  try {
    if (t) sessionStorage.setItem(TOKEN_KEY, t)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable: token lives only in memory */
  }
}

const detail = async (res: Response) => {
  const body = await res.json().catch(() => ({}))
  return typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`
}

export function useWater(): WaterController {
  const [token, setToken] = useState<string | null>(readToken)
  const [tokenError, setTokenError] = useState<string | null>(null)
  const [model, setModel] = useState<ModelStatus>({ connected: false, name: null })
  const [state, setState] = useState<WaterState>({ status: 'idle' })
  const [opacity, setOpacity] = useState(85)
  const [visible, setVisible] = useState(true)
  // Job the UI is waiting on; events for other jobs are ignored.
  const jobRef = useRef<string | null>(null)

  const regenerate = () => {
    setTokenError(null)
    fetch('/api/models/token', { method: 'POST' })
      .then(async (res) => {
        if (!res.ok) throw new Error()
        const body = (await res.json()) as { token: string }
        storeToken(body.token)
        setToken(body.token)
        setModel({ connected: false, name: null })
      })
      .catch(() => setTokenError('Could not generate the token (is the backend up to date?)'))
  }

  // Live status + job updates; opens only once the user generated a token (or one is stored). A 401 (expired token) closes the stream; get a new token.
  useEffect(() => {
    if (!token) return
    const es = new EventSource(`/api/models/events?token=${encodeURIComponent(token)}`)
    es.addEventListener('status', (ev) => {
      try {
        const d = JSON.parse((ev as MessageEvent).data) as ModelStatus
        setModel({ ...d, connected: !!d.connected, name: d.name ?? null })
      } catch {
        /* ignore malformed event */
      }
    })
    es.addEventListener('job', (ev) => {
      try {
        const d = JSON.parse((ev as MessageEvent).data) as Partial<WaterResult> & {
          job_id: string
          state: JobState
          error?: string
        }
        if (d.job_id !== jobRef.current) return
        if (d.state === 'done' && d.png_url && d.bounds) {
          jobRef.current = null
          setState({ status: 'ready', result: d as WaterResult })
          setVisible(true)
        } else if (d.state === 'error') {
          jobRef.current = null
          setState({ status: 'error', message: d.error ?? 'Model error' })
        } else if (d.state === 'queued' || d.state === 'running') {
          setState({ status: 'job', job_id: d.job_id, state: d.state })
        }
      } catch {
        /* ignore malformed event */
      }
    })
    es.onerror = () => {
      // EventSource retries on its own; if closed for good (e.g. 401), mark disconnected.
      if (es.readyState === EventSource.CLOSED) setModel({ connected: false, name: null })
    }
    return () => es.close()
  }, [token])

  const run = (bbox: BBox) => {
    if (!token) return
    setState({ status: 'job', job_id: '', state: 'queued' })
    fetch('/api/models/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ bbox }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(await detail(res))
        const body = (await res.json()) as { job_id: string }
        jobRef.current = body.job_id
        setState((s) => (s.status === 'job' ? { status: 'job', job_id: body.job_id, state: s.state } : s))
      })
      .catch((e: Error) => setState({ status: 'error', message: e.message }))
  }

  // Built-in water U-Net: synchronous POST /api/water, same state as external jobs.
  const runBuiltin = (bbox: BBox) => {
    const id = `builtin-${Date.now()}`
    jobRef.current = id
    setState({ status: 'job', job_id: id, state: 'running' })
    fetch('/api/water', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bbox }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(await detail(res))
        const body = (await res.json()) as {
          id: string
          scene_id?: string
          datetime?: string
          bounds: WaterResult['bounds']
          water_fraction?: number
          png_url: string
        }
        if (jobRef.current !== id) return
        jobRef.current = null
        setState({
          status: 'ready',
          result: {
            job_id: body.id,
            scene_id: body.scene_id,
            datetime: body.datetime,
            bounds: body.bounds,
            output: 'probability',
            label: 'Water (U-Net)',
            stats: body.water_fraction != null ? { fraction: body.water_fraction } : undefined,
            png_url: body.png_url,
          },
        })
        setVisible(true)
      })
      .catch((e: Error) => {
        if (jobRef.current !== id) return
        jobRef.current = null
        setState({ status: 'error', message: e.message })
      })
  }

  return {
    token,
    tokenError,
    model,
    state,
    opacity,
    visible,
    regenerate,
    run,
    runBuiltin,
    setOpacity,
    setVisible,
    clear: () => {
      jobRef.current = null
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
