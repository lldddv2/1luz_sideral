import { Map as MapIcon, Pentagon, RectangleHorizontal, Trash2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AoiPolygon, DrawMode } from '../types'
import type { AdminLevel } from '../regions'
import type { RegionPicker } from '../useRegionPicker'

interface Props {
  polygons: AoiPolygon[]
  mode: DrawMode | null
  regions: RegionPicker
  onSelectMode: (mode: DrawMode) => void
  onDelete: (id: string) => void
  onHoverTool: (tool: DrawMode | null) => void
}

const TOOLS: { mode: DrawMode; label: string; Icon: LucideIcon }[] = [
  { mode: 'polygon', label: 'Polígono', Icon: Pentagon },
  { mode: 'rectangle', label: 'Rectángulo', Icon: RectangleHorizontal },
  { mode: 'region', label: 'Región', Icon: MapIcon },
]

const HINTS: Record<DrawMode, string> = {
  polygon:
    'Clic para añadir vértices. Doble clic, Enter o clic en el primer vértice para cerrar. Retroceso borra el último vértice. Esc cancela.',
  rectangle: 'Clic en una esquina y clic en la esquina opuesta. Esc cancela.',
  region: '',
}

const LEVELS: { level: AdminLevel; label: string }[] = [
  { level: 'ADM0', label: 'País' },
  { level: 'ADM1', label: 'Depto./Estado' },
  { level: 'ADM2', label: 'Municipio' },
]

function RegionOptions({ regions }: { regions: RegionPicker }) {
  const { level, zoom, country, status } = regions
  return (
    <div className="region-options">
      <p className="hint level-auto">
        Nivel automático:{' '}
        {LEVELS.map((l, i) => (
          <span key={l.level}>
            {i > 0 && ' | '}
            <span className={level === l.level ? 'active' : undefined}>{l.label}</span>
          </span>
        ))}{' '}
        (zoom {zoom.toFixed(1)})
      </p>
      <p className="hint">
        {status ??
          (level === 'ADM0'
            ? 'Clic en un país para agregarlo.'
            : country
              ? `${country.name}: clic en una subdivisión para agregarla, o en otro país para cambiar.`
              : 'Clic en un país para ver sus subdivisiones.')}
      </p>
    </div>
  )
}

export default function PolygonPanel({ polygons, mode, regions, onSelectMode, onDelete, onHoverTool }: Props) {
  return (
    <aside className="panel">
      <div className="btn-row">
        {TOOLS.map((t) => (
          <button
            key={t.mode}
            className={mode === t.mode ? 'btn btn-active' : 'btn'}
            onClick={() => onSelectMode(t.mode)}
            onMouseEnter={() => onHoverTool(t.mode)}
            onMouseLeave={() => onHoverTool(null)}
          >
            <t.Icon size={16} />
            {t.label}
          </button>
        ))}
      </div>
      {mode === 'region' ? <RegionOptions regions={regions} /> : mode && <p className="hint">{HINTS[mode]}</p>}
      {polygons.length > 0 && (
        <ul className="polygon-list">
          {polygons.map((p) => (
            <li key={p.id}>
              <span>
                {p.name}
                {p.kind === 'polygon' && <small> ({p.coords.length} vértices)</small>}
              </span>
              <button className="btn-icon" onClick={() => onDelete(p.id)} title={`Eliminar ${p.name}`} aria-label={`Eliminar ${p.name}`}>
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
