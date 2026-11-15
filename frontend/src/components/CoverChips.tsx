import { CircleX, Loader2, Tags, X } from 'lucide-react'
import { formatPercent } from '../landcover'
import type { CoverChip } from '../landcover'

interface Props {
  chips: CoverChip[]
  loading: boolean // the mask of these classes is on its way; each chip shows a spinner in place of its dot
  error: string | null // the mask failed
  onRemove: (key: string) => void
  labels?: { name: string; count: number; onClear: () => void } | null // natural-feature labels on the map
}

// Active land-cover filter under the search bar: one chip per class, removed with its own ×.
export default function CoverChips({ chips, loading, error, onRemove, labels }: Props) {
  if (chips.length === 0 && !labels) return null
  return (
    <div className="cover-filter">
      <div className="cover-chips" role="group" aria-label="Land cover filter">
        {labels && (
          <span className="cover-chip">
            <Tags size={14} aria-hidden="true" />
            <span className="cover-chip-name">{labels.name}</span>
            <span className="cover-chip-percent">{labels.count}</span>
            <button
              type="button"
              className="cover-chip-remove"
              title="Remove labels from map"
              aria-label="Remove labels from map"
              onClick={labels.onClear}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </span>
        )}
        {chips.map((chip) => (
          <span key={chip.key} className="cover-chip">
            {loading ? (
              <Loader2 size={14} className="spin" aria-hidden="true" />
            ) : (
              <span className="cover-dot" style={{ background: chip.color }} aria-hidden="true" />
            )}
            <span className="cover-chip-name">{chip.name}</span>
            {chip.percent !== null && <span className="cover-chip-percent">{formatPercent(chip.percent)}</span>}
            <button
              type="button"
              className="cover-chip-remove"
              title={`Remove ${chip.name}`}
              aria-label={`Remove ${chip.name}`}
              onClick={() => onRemove(chip.key)}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </span>
        ))}
      </div>
      {error && (
        <p className="cover-error" role="status">
          <CircleX size={16} aria-hidden="true" />
          <span>Error: {error}</span>
        </p>
      )}
    </div>
  )
}
