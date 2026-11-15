import type { KeyboardEvent, ReactNode } from 'react'
import { ChevronLeft, ChevronRight, CircleX, Loader2, Pause, Play, TriangleAlert } from 'lucide-react'
import { axisLabels, groupsIn, orbitName, passSummary, rangeBounds, shortDay, timeMs, utcLabel } from '../passes'
import type { DateRange, PassEntry } from '../passes'

// Up to this many passes, each point shows its day on the line. More leave the day to the hover.
const SHORT_LABEL_MAX = 12

const share = (f: number) => `${f * 100}%`

interface Props {
  range: DateRange | null // Descarga dates; null while they are incomplete or reversed
  entry: PassEntry | undefined // passes of the active area; undefined until its search starts
  children?: ReactNode // extra row on top
  picked?: string[] // YYYY-MM-DD dates of the active water layers; matching passes are highlighted
  onPick?: (day: string) => void // click on a pass: its UTC day
  prefetch?: { done: number; total: number; paused?: boolean; stage?: string } | null // NISAR tile prefetch, then frame build progress
  playing?: boolean // timeline animation running
  onTogglePlay?: () => void // play/pause; undefined hides the button
}

// Radar passes of the active area over the Descarga range: one line, a point per pass, a date axis below.
export default function AcquisitionTimeline({ range, entry, children, picked = [], onPick, prefetch, playing = false, onTogglePlay }: Props) {
  if (!range) {
    return (
      <section data-tour="timeline" className="acq-bar" aria-label="Adquisiciones NISAR">
        <p className="acq-note">
          <TriangleAlert size={16} aria-hidden="true" />
          <span>Revisa el rango de fechas en Descarga.</span>
        </p>
      </section>
    )
  }

  const { start, end } = rangeBounds(range)
  const place = (t: number) => (t - start) / (end - start)
  const groups = entry?.status === 'ready' ? groupsIn(entry.products, range) : []
  const points = groups.flatMap((group) =>
    group.products.map((product) => {
      const t = timeMs(product)
      return {
        key: product.product_id,
        color: group.color,
        f: place(t),
        day: shortDay(t),
        iso: new Date(t).toISOString().slice(0, 10),
        tip: `${utcLabel(product.acquisition_start)} · ${orbitName(group)}`,
      }
    }),
  )
  const labels = axisLabels(range)

  // Distinct pass days in order; the arrows step through them from the first picked day.
  const days = [...new Set(points.map((p) => p.iso))].sort()
  const base = [...picked].sort().find((d) => days.includes(d)) ?? picked[0]
  const prevDay = base ? days.filter((d) => d < base).pop() : days[days.length - 1]
  const nextDay = base ? days.find((d) => d > base) : days[0]
  const step = (day: string | undefined) => day && onPick?.(day)
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft' && prevDay) (e.preventDefault(), step(prevDay))
    else if (e.key === 'ArrowRight' && nextDay) (e.preventDefault(), step(nextDay))
  }

  let note: ReactNode = null
  if (!entry || entry.status === 'loading') {
    note = (
      <p className="acq-msg">
        <Loader2 size={16} className="spin" aria-hidden="true" />
        <span>Consultando adquisiciones NISAR…</span>
      </p>
    )
  } else if (entry.status === 'error') {
    note = (
      <p className="acq-msg is-error">
        <CircleX size={16} aria-hidden="true" />
        <span>Error: {entry.message}</span>
      </p>
    )
  } else if (points.length === 0) {
    note = <p className="acq-msg">No se registraron adquisiciones NISAR en el periodo seleccionado.</p>
  }

  return (
    <section data-tour="timeline" className="acq-bar" aria-label="Adquisiciones NISAR en el periodo">
      {children}
      {groups.length > 0 && (
        <div className="acq-head">
          <ul className="acq-legend">
            {groups.map((group) => (
              <li key={group.key}>
                <span className="acq-swatch" style={{ background: group.color }} aria-hidden="true" />
                {orbitName(group)}
              </li>
            ))}
          </ul>
          <span className="acq-summary">{passSummary(groups)}</span>
          {prefetch && (
            <span className="acq-summary">
              {prefetch.total ? `${prefetch.stage ?? "Precargando"} ${Math.min(prefetch.done, prefetch.total)}/${prefetch.total}${prefetch.paused ? " (en pausa)" : ""}` : "Preparando…"}
            </span>
          )}
          <span className="acq-nav">
            {onTogglePlay && (
              <button
                type="button"
                title={playing ? 'Pausar' : 'Reproducir'}
                aria-label={playing ? 'Pausar' : 'Reproducir'}
                aria-pressed={playing}
                onClick={onTogglePlay}
              >
                {playing ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
              </button>
            )}
            <button type="button" title="Pasada anterior" aria-label="Pasada anterior" disabled={!prevDay} onClick={() => step(prevDay)}>
              <ChevronLeft size={16} aria-hidden="true" />
            </button>
            <button type="button" title="Pasada siguiente" aria-label="Pasada siguiente" disabled={!nextDay} onClick={() => step(nextDay)}>
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          </span>
        </div>
      )}
      <div className="acq-track" onKeyDown={onKey}>
        <span className="acq-line" aria-hidden="true" />
        {labels
          .filter((l) => l.align === 'middle')
          .map((l) => (
            <span key={l.f} className="acq-grid" style={{ left: share(l.f) }} aria-hidden="true" />
          ))}
        {points.map((p) => (
          <button
            type="button"
            key={p.key}
            aria-label={`${p.tip}. Usar esta fecha en las capas de agua`}
            aria-pressed={picked.includes(p.iso)}
            onClick={() => onPick?.(p.iso)}
            className={`acq-point ${p.f < 0.5 ? 'acq-point-start' : 'acq-point-end'}${picked.includes(p.iso) ? ' is-picked' : ''}`}
            style={{ left: share(p.f), background: p.color }}
          >
            {points.length <= SHORT_LABEL_MAX && (
              <span className="acq-short" aria-hidden="true">
                {p.day}
              </span>
            )}
            <span className="acq-tip" aria-hidden="true">
              {p.tip}
            </span>
          </button>
        ))}
        {note}
      </div>
      <div className="acq-axis">
        {labels.map((l) => (
          <span key={l.f} className={`acq-tick acq-tick-${l.align}`} style={{ left: share(l.f) }}>
            {l.text}
          </span>
        ))}
      </div>
    </section>
  )
}
