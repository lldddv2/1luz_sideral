import { useEffect, useRef, useState } from 'react'
import type { DownloadTarget, EstimateResult, Job } from './types'
import {
  DEFAULT_START,
  ESTIMATE_DEBOUNCE_MS,
  MAX_SEARCH_PRODUCTS,
  POL_VARIABLE,
  POLL_MS,
  POLS,
  createJob,
  fetchEstimate,
  fetchJob,
  messageOf,
  searchProducts,
  yesterdayIso,
} from './download'
import type { Pol } from './download'

export interface DownloadParams {
  start: string // YYYY-MM-DD
  end: string // YYYY-MM-DD
  pols: Pol[] // never empty, in POLS order
}

export type RunPhase = 'idle' | 'searching' | 'queued' | 'running' | 'done' | 'failed' | 'empty' | 'error'

export interface RunState {
  phase: RunPhase
  message: string | null // error text for 'failed' and 'error'
  inventoryId: string | null // set by the search; the estimate then sizes the products it found
  productCount: number | null
  job: Job | null
}

const IDLE: RunState = { phase: 'idle', message: null, inventoryId: null, productCount: null, job: null }

// Lives in App, not in the sidebar section, so a running job keeps polling when the user switches sections.
// The area is the selected point-of-interest square; study areas only scope searches.
export function useDownload(area: DownloadTarget | null) {
  const [params, setParams] = useState<DownloadParams>(() => ({
    start: DEFAULT_START,
    end: yesterdayIso(),
    pols: ['HH'],
  }))
  const [run, setRun] = useState<RunState>(IDLE)
  const [estimate, setEstimate] = useState<EstimateResult | null>(null)
  const [estimateError, setEstimateError] = useState<string | null>(null)
  const [estimating, setEstimating] = useState(false)
  // Bumped on every reset, so a search or job creation still in flight cannot write stale state.
  const generation = useRef(0)

  const polsKey = params.pols.join(',')
  const variableCount = params.pols.length
  const inventoryId = run.inventoryId
  const jobId = run.job?.id ?? null
  // Only the square matters to the run: renaming the point must not reset it. App keeps this object stable.
  const geometry = area?.geometry ?? null

  // A new area, dates or polarizations makes the current run stale: its files no longer match the inputs.
  useEffect(() => {
    generation.current += 1
    setRun(IDLE)
  }, [geometry, params.start, params.end, polsKey])

  // Before a search the estimate covers one product (the product count is unknown); after one, the products it found.
  useEffect(() => {
    if (!geometry) {
      setEstimate(null)
      setEstimateError(null)
      setEstimating(false)
      return
    }
    const controller = new AbortController()
    setEstimating(true)
    const timer = window.setTimeout(async () => {
      try {
        const body = inventoryId
          ? { geometry, variables: variableCount, inventory_id: inventoryId }
          : { geometry, variables: variableCount }
        setEstimate(await fetchEstimate(body, controller.signal))
        setEstimateError(null)
      } catch (err) {
        if (controller.signal.aborted) return
        setEstimate(null)
        setEstimateError(messageOf(err))
      } finally {
        if (!controller.signal.aborted) setEstimating(false)
      }
    }, ESTIMATE_DEBOUNCE_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [geometry, variableCount, inventoryId])

  // Poll the job every POLL_MS until it finishes. Clearing the job (a reset) stops the loop.
  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    let timer = 0
    const poll = async () => {
      try {
        const job = await fetchJob(jobId)
        if (cancelled) return
        const finished = job.state === 'done' || job.state === 'failed'
        setRun((prev) => ({ ...prev, phase: job.state, job, message: finished ? job.error : null }))
        if (!finished) timer = window.setTimeout(poll, POLL_MS)
      } catch (err) {
        if (!cancelled) setRun((prev) => ({ ...prev, phase: 'error', message: messageOf(err) }))
      }
    }
    timer = window.setTimeout(poll, POLL_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [jobId])

  const togglePol = (pol: Pol) =>
    setParams((prev) => {
      const next = prev.pols.includes(pol) ? prev.pols.filter((p) => p !== pol) : [...prev.pols, pol]
      return next.length === 0 ? prev : { ...prev, pols: POLS.filter((p) => next.includes(p)) }
    })

  // Dates never pass yesterday: a later one is clamped to it. Sidebar and search bar both write here.
  const setDates = (patch: Partial<Pick<DownloadParams, 'start' | 'end'>>) => {
    const latest = yesterdayIso()
    const cap = (date: string | undefined) => (date !== undefined && date > latest ? latest : date)
    setParams((prev) => ({
      ...prev,
      start: cap(patch.start) ?? prev.start,
      end: cap(patch.end) ?? prev.end,
    }))
  }

  const busy = run.phase === 'searching' || run.phase === 'queued' || run.phase === 'running'
  const datesOk = params.start !== '' && params.end !== '' && params.start <= params.end
  const canStart = geometry !== null && datesOk && !busy

  // Search, then create one job over every product found, for the chosen polarizations.
  const start = async () => {
    if (!geometry || !canStart) return
    const current = ++generation.current
    const stale = () => current !== generation.current
    const { start: from, end: to, pols } = params
    setRun({ ...IDLE, phase: 'searching' })
    try {
      const found = await searchProducts(
        geometry,
        `${from}T00:00:00Z`,
        `${to}T23:59:59Z`,
        MAX_SEARCH_PRODUCTS,
      )
      if (stale()) return
      const productIds = found.products.map((p) => p.product_id)
      const productCount = productIds.length
      if (productCount === 0) {
        setRun({ ...IDLE, phase: 'empty', inventoryId: found.inventory_id, productCount })
        return
      }
      setRun({ ...IDLE, phase: 'queued', inventoryId: found.inventory_id, productCount })
      const job = await createJob(found.inventory_id, productIds, pols.map((p) => POL_VARIABLE[p]))
      if (stale()) return
      setRun((prev) => ({ ...prev, phase: job.state, job }))
    } catch (err) {
      if (!stale()) setRun({ ...IDLE, phase: 'error', message: messageOf(err) })
    }
  }

  return {
    area,
    params,
    setDates,
    togglePol,
    datesOk,
    estimate,
    estimateError,
    estimating,
    run,
    canStart,
    start,
  }
}

export type DownloadController = ReturnType<typeof useDownload>
