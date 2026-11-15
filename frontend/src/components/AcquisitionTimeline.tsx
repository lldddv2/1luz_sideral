import type { ReactNode } from 'react'
import { CircleX, Loader2, TriangleAlert } from 'lucide-react'
import { axisLabels, groupsIn, orbitName, passSummary, rangeBounds, shortDay, timeMs, utcLabel } from '../passes'
import type { DateRange, PassEntry } from '../passes'

// Up to this many passes, each point shows its day on the line. More leave the day to the hover.
const SHORT_LABEL_MAX = 12

const share = (f: number) => `${f * 100}%`

interface Props {
  range: DateRange | null // Descarga dates; null while they are incomplete or reversed
  entry: PassEntry | undefined // passes of the active area; undefined until its search starts
  children?: ReactNode // extra row on top
}

// Radar passes of the active area over the Descarga range: one line, a point per pass, a date axis below.
export default function AcquisitionTimeline({ range, entry, children }: Props) {
  if (!range) {
    return (
      <section className="acq-bar" aria-label="Adquisiciones NISAR">
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
        tip: `${utcLabel(product.acquisition_start)} · ${orbitName(group)}`,
      }
    }),
  )
  const labels = axisLabels(range)

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
    <section className="acq-bar" aria-label="Adquisiciones NISAR en el periodo">
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
        </div>
      )}
      <div className="acq-track">
        <span className="acq-line" aria-hidden="true" />
        {labels
          .filter((l) => l.align === 'middle')
          .map((l) => (
            <span key={l.f} className="acq-grid" style={{ left: share(l.f) }} aria-hidden="true" />
          ))}
        {points.map((p) => (
          <span
            key={p.key}
            role="img"
            aria-label={p.tip}
            className={p.f < 0.5 ? 'acq-point acq-point-start' : 'acq-point acq-point-end'}
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
          </span>
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
