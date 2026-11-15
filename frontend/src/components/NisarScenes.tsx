import { Check, Loader2, Plus, Satellite } from 'lucide-react'
import { sceneLabel } from '../nisarScenes'
import type { NisarScenesController } from '../useNisarScenes'
import type { NisarPol } from '../types'

const POLS: NisarPol[] = ['HH', 'HV']

// Row of NISAR scenes stored in S3 for the active area: one button per scene, HH/HV and overlay opacity.
export default function NisarScenes({ nisar }: { nisar: NisarScenesController }) {
  if (nisar.scenes.length === 0) return null
  return (
    <div className="nisar-row" role="group" aria-label="Escenas NISAR en S3">
      <span className="nisar-title">
        {nisar.loading ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <Satellite size={16} aria-hidden="true" />}
        Escenas NISAR
      </span>
      {nisar.scenes.map((s) => {
        const on = s.scene_id === nisar.selected
        return (
          <button
            key={s.scene_id}
            type="button"
            className={on ? 'btn btn-active nisar-scene' : 'btn nisar-scene'}
            aria-pressed={on}
            title={s.scene_id}
            onClick={() => nisar.setSelected(on ? null : s.scene_id)}
          >
            {on ? <Check size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}
            {sceneLabel(s)}
          </button>
        )
      })}
      <div className="segmented" role="group" aria-label="Polarización">
        {POLS.map((p) => (
          <button
            key={p}
            type="button"
            className={nisar.pol === p ? 'btn btn-active' : 'btn'}
            aria-pressed={nisar.pol === p}
            onClick={() => nisar.setPol(p)}
          >
            {nisar.pol === p ? <Check size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}
            {p}
          </button>
        ))}
      </div>
      <label className="nisar-opacity">
        Opacidad
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={nisar.opacity}
          onChange={(e) => nisar.setOpacity(Number(e.target.value))}
        />
      </label>
    </div>
  )
}
