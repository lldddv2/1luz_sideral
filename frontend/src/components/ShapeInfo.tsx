import { geometryAreaKm2, geometryBbox, shapeGeometry } from '../geo'
import type { AoiPolygon } from '../types'

const KIND_LABEL = { polygon: 'Polígono', rectangle: 'Rectángulo', region: 'Región administrativa' } as const

const fmt = (n: number, digits = 2) => n.toLocaleString('es', { maximumFractionDigits: digits })

export default function ShapeInfo({ shape }: { shape: AoiPolygon }) {
  const geometry = shapeGeometry(shape)
  const [w, s, e, n] = geometryBbox(geometry)
  return (
    <>
      <h3>{shape.name}</h3>
      <dl>
        <dt>Tipo</dt>
        <dd>{KIND_LABEL[shape.kind]}</dd>
        <dt>Área</dt>
        <dd>{fmt(geometryAreaKm2(geometry), 1)} km²</dd>
        {shape.kind === 'polygon' && (
          <>
            <dt>Vértices</dt>
            <dd>{shape.coords.length}</dd>
          </>
        )}
        <dt>BBox</dt>
        <dd>{[w, s, e, n].map((v) => v.toFixed(3)).join(', ')}</dd>
      </dl>
      <p className="info-hint">
        {shape.kind === 'region'
          ? 'Límite oficial: no editable. Clic derecho para más opciones.'
          : 'Clic para editar: arrastra vértices, lados o la figura; el punto verde gira. Clic derecho para más opciones.'}
      </p>
    </>
  )
}
