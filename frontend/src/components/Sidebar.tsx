import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  Check,
  CircleAlert,
  CircleCheck,
  ChevronDown,
  CircleX,
  Clock,
  Download,
  Droplets,
  FileDown,
  Info,
  Layers,
  Loader2,
  Map as MapIcon,
  MapPin,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Pentagon,
  Plus,
  RectangleHorizontal,
  ScanSearch,
  Trash2,
  TriangleAlert,
  Trees,
  Plug,
  Copy,
  RefreshCw,
  Play,
  BookOpen,
  X,
} from 'lucide-react'
import { Compass } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { startTour } from '../tour'
import type { AoiPolygon, DrawMode, UserZone } from '../types'
import type { AdminLevel } from '../regions'
import type { RegionPicker } from '../useRegionPicker'
import type { DownloadController, RunPhase, RunState } from '../useDownload'
import type { LandcoverController } from '../useLandcover'
import { formatPercent } from '../landcover'
import { MAX_SEARCH_PRODUCTS, POLL_MS, POLS, fileUrl, formatKm2, warningsFor, yesterdayIso } from '../download'
import { BASEMAPS } from '../basemaps'
import type { BasemapId } from '../basemaps'
import { NISAR_ASC_COLOR, NISAR_DESC_COLOR, OVERLAYS, OVERLAY_IDS } from '../layers'
import { ZONE_MAX_SIDE_KM, ZONE_MIN_SIDE_KM, clampHalfKm } from '../zone'
import type { OverlayId, OverlayState } from '../layers'
import type { WaterController, WaterResult } from '../water'
import type { BBox } from '../nominatim'

// Legend color per water layer, shown as a dot next to its name.
const LAYER_DOT: Record<OverlayId, string> = { dswx: '#1f78b4', nisar: '#7b3fbf', jrc: '#14a3a3' }

type SectionId = 'study' | 'zones' | 'cover' | 'download' | 'water' | 'layers' | 'about'

interface Props {
  polygons: AoiPolygon[]
  mode: DrawMode | null
  regions: RegionPicker
  download: DownloadController
  cover: LandcoverController
  basemap: BasemapId
  onSelectMode: (mode: DrawMode) => void
  onDelete: (id: string) => void
  onHoverTool: (tool: DrawMode | null) => void
  onBasemapChange: (basemap: BasemapId) => void
  overlays: Record<OverlayId, OverlayState>
  onOverlayChange: (id: OverlayId, patch: Partial<OverlayState>) => void
  zones: UserZone[]
  selectedZoneId: string | null
  onSelectZone: (id: string | null) => void
  zonePlacing: boolean
  onToggleZonePlacing: () => void
  onZoneChange: (zone: UserZone) => void
  onFocusZone: (id: string) => void
  onDeleteZone: (id: string) => void
  aoiFill: number // study area fill opacity, 0-100 (0: outline only)
  onAoiFill: (v: number) => void
  zoneFill: number // point of interest fill opacity, 0-100
  onZoneFill: (v: number) => void
  water: WaterController
  waterTarget: { name: string; bbox: BBox } | null // area the U-Net runs on
}

// Fill opacity slider shared by the study area and point of interest sections.
function FillSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="field">
      <span className="field-label">
        Opacidad del relleno <span className="layer-pct">{value}%</span>
      </span>
      <input
        className="slider"
        type="range"
        min={0}
        max={100}
        step={1}
        value={value}
        style={{ '--pct': `${value}%` } as CSSProperties}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="Opacidad del relleno"
        aria-valuetext={`${value}%`}
      />
    </div>
  )
}

const SECTIONS: { id: SectionId; label: string; Icon: LucideIcon }[] = [
  { id: 'study', label: 'Área de estudio', Icon: Pentagon },
  { id: 'zones', label: 'Puntos de interés', Icon: MapPin },
  { id: 'cover', label: 'Coberturas', Icon: Trees },
  { id: 'download', label: 'Descarga', Icon: Download },
  { id: 'water', label: 'Modelo propio', Icon: Plug },
  { id: 'layers', label: 'Capas', Icon: Layers },
  { id: 'about', label: 'Acerca', Icon: Info },
]

// Shared with the map tool palette so icons and labels are never duplicated.
export const TOOLS: { mode: DrawMode; label: string; Icon: LucideIcon }[] = [
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

// localStorage is unavailable in some privacy modes; the UI must still work.
const STORAGE_COLLAPSED = 'luz-sideral:sidebar-collapsed'
const STORAGE_SECTION = 'luz-sideral:sidebar-section'

const readStoredCollapsed = () => {
  try {
    return localStorage.getItem(STORAGE_COLLAPSED) === '1'
  } catch {
    return false
  }
}

const readStoredSection = (): SectionId => {
  try {
    const raw = localStorage.getItem(STORAGE_SECTION)
    return SECTIONS.some((s) => s.id === raw) ? (raw as SectionId) : 'study'
  } catch {
    return 'study'
  }
}

const store = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Storage is optional; ignore failures.
  }
}

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

function StudyAreaSection({
  polygons,
  mode,
  regions,
  onSelectMode,
  onDelete,
  onHoverTool,
  aoiFill,
  onAoiFill,
}: Pick<Props, 'polygons' | 'mode' | 'regions' | 'onSelectMode' | 'onDelete' | 'onHoverTool' | 'aoiFill' | 'onAoiFill'>) {
  return (
    <>
      <FillSlider value={aoiFill} onChange={onAoiFill} />
      <h3 className="section-title">Herramientas de dibujo</h3>
      <div className="btn-row">
        {TOOLS.map((t) => (
          <button
            key={t.mode}
            type="button"
            className={mode === t.mode ? 'btn btn-active' : 'btn'}
            aria-pressed={mode === t.mode}
            onClick={() => onSelectMode(t.mode)}
            onMouseEnter={() => onHoverTool(t.mode)}
            onMouseLeave={() => onHoverTool(null)}
            onFocus={() => onHoverTool(t.mode)}
            onBlur={() => onHoverTool(null)}
          >
            <t.Icon size={16} />
            {t.label}
          </button>
        ))}
      </div>
      {mode === 'region' ? <RegionOptions regions={regions} /> : mode && <p className="hint">{HINTS[mode]}</p>}

      <h3 className="section-title">
        Áreas de estudio
        <span className="count">{polygons.length}</span>
      </h3>
      {polygons.length > 0 ? (
        <ul className="polygon-list">
          {polygons.map((p) => (
            <li key={p.id}>
              <span className="polygon-name">
                {p.name}
                {p.kind === 'polygon' && <small> ({p.coords.length} vértices)</small>}
              </span>
              <button
                type="button"
                className="btn-icon"
                onClick={() => onDelete(p.id)}
                title={`Eliminar ${p.name}`}
                aria-label={`Eliminar ${p.name}`}
              >
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-state">Aún no hay áreas. Dibuja un polígono o elige una región.</p>
      )}
    </>
  )
}

type ZonesProps = Pick<
  Props,
  | 'zones'
  | 'selectedZoneId'
  | 'onSelectZone'
  | 'zonePlacing'
  | 'onToggleZonePlacing'
  | 'onZoneChange'
  | 'onFocusZone'
  | 'onDeleteZone'
  | 'zoneFill'
  | 'onZoneFill'
>

function ZonesSection({
  zones,
  selectedZoneId,
  onSelectZone,
  zonePlacing,
  onToggleZonePlacing,
  onZoneChange,
  onFocusZone,
  onDeleteZone,
  zoneFill,
  onZoneFill,
}: ZonesProps) {
  return (
    <>
      <FillSlider value={zoneFill} onChange={onZoneFill} />
      <h3 className="section-title">Marcar</h3>
      <div className="btn-row">
        <button
          type="button"
          className={zonePlacing ? 'btn btn-active' : 'btn'}
          aria-pressed={zonePlacing}
          onClick={onToggleZonePlacing}
        >
          <MapPin size={16} aria-hidden="true" />
          Marcar punto
        </button>
      </div>
      <p className="hint">
        {zonePlacing
          ? 'Haz clic en el mapa para fijar el centro. Esc cancela.'
          : zones.length
            ? 'Arrastra un centro para mover su cuadrado y una esquina del seleccionado para cambiar el rango.'
            : 'Señala puntos de interés con un rango cuadrado. No cambian el área de estudio.'}
      </p>

      {zones.length ? (
        <>
          <h3 className="section-title">Puntos de interés</h3>
          <ul className="zone-list">
            {zones.map((zone, i) => {
              const selected = zone.id === selectedZoneId
              return (
                <li key={zone.id} className={selected ? 'zone-item zone-item-selected' : 'zone-item'}>
                  <button
                    type="button"
                    className="zone-item-head"
                    aria-expanded={selected}
                    onClick={() => onSelectZone(selected ? null : zone.id)}
                  >
                    <MapPin size={14} aria-hidden="true" />
                    <span className="zone-item-name">{zone.name || `Punto ${i + 1}`}</span>
                    <span className="zone-coords">
                      {zone.center[1].toFixed(3)}, {zone.center[0].toFixed(3)}
                    </span>
                  </button>
                  {selected && (
                    <ZoneEditor zone={zone} onZoneChange={onZoneChange} onFocusZone={onFocusZone} onDeleteZone={onDeleteZone} />
                  )}
                </li>
              )
            })}
          </ul>
        </>
      ) : (
        <p className="empty-state">Aún no hay puntos. Pulsa «Marcar punto» y haz clic en el mapa.</p>
      )}
    </>
  )
}

function ZoneEditor({
  zone,
  onZoneChange,
  onFocusZone,
  onDeleteZone,
}: { zone: UserZone } & Pick<Props, 'onZoneChange' | 'onFocusZone' | 'onDeleteZone'>) {
  const sideKm = Math.round(zone.halfSizeKm * 2 * 10) / 10
  const setSide = (km: number) => {
    if (Number.isFinite(km)) onZoneChange({ ...zone, halfSizeKm: clampHalfKm(km / 2) })
  }
  return (
    <div className="zone-editor">
      <div className="field">
        <span className="field-label">Centro</span>
        <span className="zone-coords">
          {zone.center[1].toFixed(5)}, {zone.center[0].toFixed(5)}
        </span>
      </div>
      <div className="field">
        <label className="field-row field-row-label" htmlFor="zone-side">
          <span className="field-label">Rango (lado)</span>
          <span className="zone-side-input">
            <input
              id="zone-side"
              className="input"
              type="number"
              min={ZONE_MIN_SIDE_KM}
              max={ZONE_MAX_SIDE_KM}
              step={0.5}
              value={sideKm}
              onChange={(e) => setSide(Number(e.target.value))}
            />
            km
          </span>
        </label>
        <input
          className="slider"
          type="range"
          min={ZONE_MIN_SIDE_KM}
          max={ZONE_MAX_SIDE_KM}
          step={0.5}
          value={sideKm}
          onChange={(e) => setSide(Number(e.target.value))}
          aria-label="Rango"
          aria-valuetext={`${sideKm} km`}
        />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="zone-name">
          Nombre
        </label>
        <input
          id="zone-name"
          className="input"
          value={zone.name ?? ''}
          placeholder="Opcional"
          onChange={(e) => onZoneChange({ ...zone, name: e.target.value || undefined })}
        />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="zone-note">
          Nota
        </label>
        <textarea
          id="zone-note"
          className="input zone-note-input"
          rows={2}
          value={zone.note ?? ''}
          placeholder="Opcional"
          onChange={(e) => onZoneChange({ ...zone, note: e.target.value || undefined })}
        />
      </div>
      <div className="btn-row">
        <button type="button" className="btn" onClick={() => onFocusZone(zone.id)}>
          <ScanSearch size={16} aria-hidden="true" />
          Ir a
        </button>
        <button type="button" className="btn" onClick={() => onDeleteZone(zone.id)}>
          <Trash2 size={16} aria-hidden="true" />
          Eliminar
        </button>
      </div>
    </div>
  )
}

function LayersSection({
  basemap,
  onBasemapChange,
  overlays,
  onOverlayChange,
}: Pick<Props, 'basemap' | 'onBasemapChange' | 'overlays' | 'onOverlayChange'>) {
  const [waterOpen, setWaterOpen] = useState(true)
  return (
    <>
      <h3 className="section-title">Mapa base</h3>
      <div className="option-list" role="radiogroup" aria-label="Mapa base">
        {Object.values(BASEMAPS).map((b) => (
          <button
            key={b.id}
            type="button"
            role="radio"
            aria-checked={basemap === b.id}
            className={basemap === b.id ? 'option option-active' : 'option'}
            onClick={() => onBasemapChange(b.id)}
          >
            <span className="option-swatch" data-swatch={b.id} aria-hidden="true" />
            <span className="option-text">
              <span className="option-label">{b.label}</span>
              <span className="option-hint">{b.hint}</span>
            </span>
          </button>
        ))}
      </div>

      <button
        type="button"
        className="section-title section-toggle"
        aria-expanded={waterOpen}
        aria-controls="water-layers"
        onClick={() => setWaterOpen((v) => !v)}
      >
        <span>Capas de agua</span>
        <ChevronDown size={16} className="section-chevron" aria-hidden="true" />
      </button>
      <div id="water-layers" className={waterOpen ? 'collapse collapse-open' : 'collapse'}>
        <div className="collapse-inner">
      {OVERLAY_IDS.map((id) => {
        const o = OVERLAYS[id]
        const st = overlays[id]
        return (
          <div className={st.on ? 'layer-card layer-card-on' : 'layer-card'} key={id}>
            <label className="layer-head">
              <input type="checkbox" checked={st.on} onChange={(e) => onOverlayChange(id, { on: e.target.checked })} />
              <span className="layer-dot" style={{ background: LAYER_DOT[id] }} aria-hidden="true" />
              <span className="layer-name" title={o.hint}>
                {o.label}
              </span>
              <span className="layer-pct">{st.opacity}%</span>
            </label>
            <div className="layer-body">
            <input
              className="slider layer-slider"
              type="range"
              min={0}
              max={100}
              step={5}
              value={st.opacity}
              disabled={!st.on}
              style={{ '--pct': `${st.opacity}%` } as CSSProperties}
              onChange={(e) => onOverlayChange(id, { opacity: Number(e.target.value) })}
              aria-label={`Opacidad ${o.label}`}
              aria-valuetext={`${st.opacity}%`}
            />
            {o.needsDate && (
              <input
                className="input layer-date"
                type="date"
                value={st.date}
                disabled={!st.on}
                onChange={(e) => e.target.value && onOverlayChange(id, { date: e.target.value })}
                aria-label={`Fecha ${o.label}`}
              />
            )}
            {(id === 'nisar' || id === 'dswx') && <p className="layer-hint">Mosaico de 12 días hasta esta fecha</p>}
            {id === 'nisar' && (
              <div className="layer-sub">
              <label className="layer-check">
                <input
                  type="checkbox"
                  checked={st.outline ?? true}
                  disabled={!st.on}
                  onChange={(e) => onOverlayChange(id, { outline: e.target.checked })}
                />
                <span>Contorno de órbitas</span>
              </label>
              <p className="layer-hint">
                {(st.outline ?? true) ? 'Alejado: contorno de órbitas · cerca: mosaico a color' : 'Mosaico visible al acercar'}
              </p>
              </div>
            )}
            {id === 'nisar' && (
              // Orbit pass filter: its own group (it filters both the image and the outline).
              // At least one direction stays on: the last checked box is disabled.
              <div className="layer-sub" role="group" aria-label="Pasadas NISAR">
              <span className="layer-hint">Pasadas:</span>
              {(
                [
                  ['asc', 'Ascendente', NISAR_ASC_COLOR],
                  ['desc', 'Descendente', NISAR_DESC_COLOR],
                ] as const
              ).map(([k, label, color]) => {
                const checked = st[k] ?? true
                const other = (k === 'asc' ? st.desc : st.asc) ?? true
                return (
                  <label key={k} className="layer-check" title={checked && !other ? 'Debe quedar al menos una pasada' : undefined}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!st.on || (checked && !other)}
                      onChange={(e) => (e.target.checked || other) && onOverlayChange(id, { [k]: e.target.checked })}
                    />
                    <span className="layer-dot layer-dot-sm" style={{ background: color }} aria-hidden="true" />
                    <span>{label}</span>
                  </label>
                )
              })}
              <p className="layer-hint">Filtra imagen y contorno</p>
              </div>
            )}
            {id === 'nisar' && (
              <div className="segmented" role="group" aria-label="Modo NISAR">
                {(
                  [
                    ['water', 'Agua (umbral)', Droplets],
                    ['color', 'Color (suavizado)', Palette],
                  ] as const
                ).map(([m, label, Icon]) => (
                  <button
                    key={m}
                    type="button"
                    className={(st.mode ?? 'color') === m ? 'active' : undefined}
                    aria-pressed={(st.mode ?? 'color') === m}
                    disabled={!st.on}
                    onClick={() => onOverlayChange(id, { mode: m })}
                  >
                    <Icon size={16} aria-hidden="true" />
                    {label}
                  </button>
                ))}
              </div>
            )}
            {id === 'nisar' && (st.mode ?? 'color') === 'water' && (
              <p className="layer-hint">
                <span className="layer-dot layer-dot-sm" style={{ background: '#2b8cbe' }} aria-hidden="true" /> Azul = baja retrodispersión banda L (agua/superficie lisa)
              </p>
            )}
            <p className="layer-hint">{o.hint}</p>
            </div>
          </div>
        )
      })}
        </div>
      </div>
    </>
  )
}

function CopyButton({ text, label, className = 'btn' }: { text: string; label: string; className?: string }) {
  const [done, setDone] = useState(false)
  const copy = () => {
    navigator.clipboard
      ?.writeText(text)
      .then(() => {
        setDone(true)
        setTimeout(() => setDone(false), 1500)
      })
      .catch(() => {})
  }
  return (
    <button type="button" className={className} onClick={copy} title={label} aria-label={label}>
      {done ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
    </button>
  )
}

function CodeBlock({ code, label, tall }: { code: string; label: string; tall?: boolean }) {
  return (
    <div className={tall ? 'model-code tall' : 'model-code'}>
      <pre>{code}</pre>
      <CopyButton text={code} label={label} className="model-copy" />
    </div>
  )
}

const JOB_LABEL = { queued: 'En cola', running: 'Procesando' } as const

const fmt = (v: number | undefined) =>
  v == null || !Number.isFinite(v) ? '—' : Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2)

function ModelLegend({ result }: { result: WaterResult }) {
  const { legend, units, stats, output } = result
  const u = units ? ` ${units}` : ''
  return (
    <>
      {legend && 'classes' in legend ? (
        <ul className="model-classes">
          {legend.classes.map((c) => (
            <li key={c.value}>
              <span className="layer-dot layer-dot-sm" style={{ background: c.color }} aria-hidden="true" /> {c.value}
            </li>
          ))}
        </ul>
      ) : legend ? (
        <div className="model-legend">
          <div className="model-ramp" aria-hidden="true" />
          <div className="model-ramp-labels">
            <span>
              {fmt(legend.min)}
              {u}
            </span>
            <span>
              {fmt(legend.max)}
              {u}
            </span>
          </div>
        </div>
      ) : null}
      {stats && (
        <p className="hint">
          mín {fmt(stats.min)} · máx {fmt(stats.max)} · media {fmt(stats.mean)}
          {u}
          {stats.fraction != null && output !== 'continuous' && <> · {(stats.fraction * 100).toFixed(1)} % del área</>}
        </p>
      )}
    </>
  )
}

// Raster from the user's own model (any kind), running locally and connected over /api/models.
function WaterSection({ water, target }: { water: WaterController; target: Props['waterTarget'] }) {
  const { state, model, token } = water
  // Dev: the model talks to uvicorn directly (port 8000) instead of through the Vite proxy.
  const origin = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin
  const tok = token ?? '<TOKEN>'
  const auth = `-H "Authorization: Bearer ${tok}"`
  const jobId = state.status === 'job' && state.job_id ? state.job_id : '<job_id>'
  // One flag per line: bash continues with " \", PowerShell with " `".
  const sh = (...parts: string[]) => parts.join(' \\\n  ')
  const ps = (...parts: string[]) => parts.join(' `\n  ')
  const hello = [
    '{',
    '  "name": "mi-modelo",',
    '  "output": "probability",',
    '  "pols": ["HH"],',
    '  "label": "Agua",',
    '  "units": ""',
    '}',
  ]
  const ct = '-H "Content-Type: application/json"'
  const cmdHello = sh(`curl -X POST ${origin}/api/models/hello`, auth, ct, `-d '${hello.join('\n  ')}'`)
  const cmdHelloPs =
    `@'\n${hello.join('\n')}\n'@ | Set-Content -Encoding ascii hello.json\n` +
    ps(`curl.exe -X POST ${origin}/api/models/hello`, auth, ct, '-d "@hello.json"')
  const cmdNext = sh(`curl ${origin}/api/models/jobs/next`, auth)
  const inputUrl = jobId === '<job_id>' ? '<input_url>' : `/api/models/jobs/${jobId}/input.tif`
  const cmdInput = sh(`curl ${origin}${inputUrl}`, auth, '-o input.tif')
  const cmdResult = sh(`curl -X POST ${origin}/api/models/jobs/${jobId}/result`, auth, '-F "file=@result.tif;type=image/tiff"')
  const busy = state.status === 'job'
  const desc = [model.name ?? 'modelo', model.label].filter(Boolean).join(' · ')
  const dim = token ? undefined : 'model-dim'
  const [guide, setGuide] = useState(false)
  useEffect(() => {
    if (!guide) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setGuide(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [guide])
  const connectBtn = (
    <button type="button" className="btn btn-active" onClick={water.regenerate}>
      <Plug size={16} aria-hidden="true" />
      Conectar modelo
    </button>
  )
  const tokenError = water.tokenError && (
    <p className="download-status tone-error" role="alert">
      <CircleX size={16} aria-hidden="true" />
      <span>{water.tokenError}</span>
    </p>
  )
  return (
    <>
      <p className={model.connected ? 'model-status on' : 'model-status'} role="status">
        <span className="model-dot" aria-hidden="true" />
        {model.connected ? `Conectado: ${desc}` : 'Desconectado'}
      </p>
      {token ? (
        <>
          <div className="model-token-row">
            <code className="model-token" title={token}>{`${token.slice(0, 10)}…${token.slice(-4)}`}</code>
            <CopyButton text={token} label="Copiar token" className="model-icon-btn" />
            <button type="button" className="model-icon-btn" onClick={water.regenerate} title="Regenerar token" aria-label="Regenerar token">
              <RefreshCw size={16} aria-hidden="true" />
            </button>
          </div>
          {!model.connected && <p className="hint">Usa la guía para conectar tu modelo con curl.</p>}
        </>
      ) : (
        <div className="btn-row">{connectBtn}</div>
      )}
      {tokenError}
      <div className="btn-row">
        <button
          type="button"
          className="btn btn-active"
          disabled={!target || busy || !model.connected}
          onClick={() => target && water.run(target.bbox)}
        >
          {busy ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
          Ejecutar modelo
        </button>
        {state.status !== 'idle' && (
          <button type="button" className="btn" onClick={water.clear}>
            <Trash2 size={16} aria-hidden="true" />
            Quitar
          </button>
        )}
      </div>
      <p className="hint">
        {!model.connected ? 'Conecta un modelo para ejecutarlo.' : target ? <>Área: {target.name}</> : 'Elige un área (máx. 60 km).'}
      </p>
      <button type="button" className="btn model-guide-btn" onClick={() => setGuide(true)}>
        <BookOpen size={16} aria-hidden="true" />
        Guía de uso
      </button>
      {guide && (
        <div className="model-modal-backdrop" onClick={() => setGuide(false)}>
          <div
            className="model-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="model-guide-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="model-modal-head">
              <h2 id="model-guide-title">Guía de uso</h2>
              <button type="button" className="model-icon-btn" onClick={() => setGuide(false)} title="Cerrar" aria-label="Cerrar" autoFocus>
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <p className="body-text">
              Tu modelo lee <code>input.tif</code> (dB, una banda por polarización) y devuelve un GeoTIFF de 1 banda.
            </p>
            <ol className="body-text model-steps">
              <li>
                Genera un token de sesión (2 h):
                {token ? <p className="hint">Token listo; los comandos ya lo incluyen.</p> : <div className="btn-row">{connectBtn}</div>}
                {tokenError}
              </li>
              <li className={dim}>
                Presenta tu modelo:
                <CodeBlock code={cmdHello} label="Copiar comando hello" />
                <p className="hint">
                  <code>output</code>: <code>probability</code> (0–1), <code>continuous</code> o <code>classes</code>.{' '}
                  <code>pols</code>: polarizaciones que lee (HH, HV, VV, VH).
                </p>
                <details>
                  <summary>Windows PowerShell</summary>
                  <CodeBlock code={cmdHelloPs} label="Copiar comando hello (PowerShell)" />
                </details>
              </li>
              <li className={dim}>Selecciona un área y pulsa «Ejecutar modelo».</li>
              <li className={dim}>
                Toma el trabajo (devuelve <code>job_id</code> e <code>input_url</code>):
                <CodeBlock code={cmdNext} label="Copiar comando jobs/next" />
              </li>
              <li className={dim}>
                Descarga la imagen:
                <CodeBlock code={cmdInput} label="Copiar comando de descarga" />
              </li>
              <li className={dim}>
                Procesa <code>input.tif</code> con tu modelo → <code>result.tif</code> (misma malla, 1 banda float32).
              </li>
              <li className={dim}>
                Sube el resultado; aparece en el mapa:
                <CodeBlock code={cmdResult} label="Copiar comando de subida" />
              </li>
            </ol>
            <p className="hint">
              Sin actividad en 30 s pasa a Desconectado; repite hello o jobs/next para reconectar. En Windows PowerShell usa{' '}
              <code>curl.exe</code>.
            </p>
          </div>
        </div>
      )}
      {busy && (
        <p className="download-status tone-info" role="status">
          {state.state === 'queued' ? <Clock size={16} aria-hidden="true" /> : <Loader2 size={16} className="spin" aria-hidden="true" />}
          <span>{JOB_LABEL[state.state]}</span>
        </p>
      )}
      {state.status === 'error' && (
        <p className="download-status tone-error" role="alert">
          <CircleX size={16} aria-hidden="true" />
          <span>Error: {state.message}</span>
        </p>
      )}
      {state.status === 'ready' && (
        <>
          <p className="download-status tone-ok" role="status">
            <CircleCheck size={16} aria-hidden="true" />
            <span>Listo{state.result.label ? `: ${state.result.label}` : ''}</span>
          </p>
          {state.result.datetime && (
            <p className="hint" title={state.result.scene_id}>
              Escena: {state.result.datetime.slice(0, 10)}
            </p>
          )}
          <ModelLegend result={state.result} />
          <label className="field-label">
            <input type="checkbox" checked={water.visible} onChange={(e) => water.setVisible(e.target.checked)} /> Mostrar
            resultado del modelo
          </label>
          <div className="field">
            <span className="field-label">
              Opacidad <span className="layer-pct">{water.opacity}%</span>
            </span>
            <input
              className="slider"
              type="range"
              min={0}
              max={100}
              step={1}
              value={water.opacity}
              style={{ '--pct': `${water.opacity}%` } as CSSProperties}
              onChange={(e) => water.setOpacity(Number(e.target.value))}
              aria-label="Opacidad del resultado del modelo"
              aria-valuetext={`${water.opacity}%`}
            />
          </div>
        </>
      )}
    </>
  )
}

function AboutSection() {
  return (
    <>
      <h3 className="section-title">¿Qué es NISAR?</h3>
      <p className="body-text">
        NISAR es un satélite de radar de apertura sintética (SAR) desarrollado por la NASA y la ISRO. Mide
        cambios milimétricos de la superficie terrestre: humedales, incendios, sismos, cultivos, glaciares y
        hundimientos del terreno.
      </p>
      <p className="body-text">
        El radar es activo: ilumina el terreno con microondas y escucha el eco. Por eso observa de día y de
        noche, y atraviesa nubes, humo y lluvia ligera, algo imposible para un sensor óptico.
      </p>
      <h3 className="section-title">HH frente a HV</h3>
      <p className="body-text">
        <strong>HH</strong> emite y recibe en polarización horizontal: sensible a superficies rugosas y a la
        estructura del suelo. <strong>HV</strong> emite en horizontal y recibe en vertical: sensible al volumen
        de la vegetación y a la biomasa. Comparar ambas separa suelo desnudo de dosel vegetal.
      </p>
      <p className="hint">NASA Space Apps Challenge 2026 · Dancing with the SARs</p>
    </>
  )
}

// Share of each class in the active area. A bar toggles its class in the map filter, shared with the search bar.
function CoverSection({ cover }: { cover: LandcoverController }) {
  const { suggestions, toggle } = cover
  const { area, filter, classesError } = suggestions
  if (!area) return <p className="empty-state">Selecciona o dibuja un área en el mapa para ver sus coberturas.</p>
  if (classesError) return <p className="download-error">Error: {classesError}</p>
  const entry = area.stats
  if (entry?.status === 'error') return <p className="download-error">Error: {entry.message}</p>
  if (entry?.status !== 'ready') {
    return (
      <p className="cover-status">
        <Loader2 size={16} className="spin" aria-hidden="true" />
        Consultando cobertura…
      </p>
    )
  }
  const { stats } = entry
  const rows = stats.classes.filter((c) => c.percent > 0).sort((a, b) => b.percent - a.percent)
  return (
    <>
      <p className="download-area" title={area.name}>
        {area.name}
      </p>
      <ul className="cover-bars">
        {rows.map((c) => {
          const on = filter.includes(c.key)
          const Icon = on ? Check : Plus
          return (
            <li key={c.key}>
              <button
                type="button"
                className={`cover-bar${on ? ' is-active' : ''}`}
                aria-pressed={on}
                title={on ? `Quitar ${c.name} del filtro` : `Filtrar el mapa por ${c.name}`}
                onClick={() => toggle(c.key)}
              >
                <Icon size={16} aria-hidden="true" />
                <span className="cover-bar-name">{c.name}</span>
                <span className="cover-bar-value">{formatPercent(c.percent)}</span>
                <span className="cover-bar-track" aria-hidden="true">
                  <span className="cover-bar-fill" style={{ width: `${c.percent}%`, background: c.color }} />
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      <p className="hint">Clic en una cobertura para filtrar el mapa. Resolución {stats.resolution_m} m.</p>
    </>
  )
}

const RUN_STATUS: Record<
  Exclude<RunPhase, 'idle'>,
  { label: string; Icon: LucideIcon; tone: 'busy' | 'ok' | 'error' | 'muted'; spin?: boolean }
> = {
  searching: { label: 'Buscando', Icon: Loader2, tone: 'busy', spin: true },
  queued: { label: 'En cola', Icon: Clock, tone: 'busy' },
  running: { label: 'Procesando', Icon: Loader2, tone: 'busy', spin: true },
  done: { label: 'Listo', Icon: CircleCheck, tone: 'ok' },
  failed: { label: 'Error', Icon: CircleX, tone: 'error' },
  error: { label: 'Error', Icon: CircleX, tone: 'error' },
  empty: { label: 'Sin datos NISAR para esta región y fechas', Icon: CircleAlert, tone: 'muted' },
}

function RunStatus({ run }: { run: RunState }) {
  if (run.phase === 'idle') return null
  const { label, Icon, tone, spin } = RUN_STATUS[run.phase]
  const job = run.job
  const failed = job?.results.filter((r) => r.state !== 'downloaded' && r.error) ?? []
  return (
    <>
      <p className={`download-status tone-${tone}`} role="status">
        <Icon size={16} className={spin ? 'spin' : undefined} aria-hidden="true" />
        <span>
          {label}
          {run.message && `: ${run.message}`}
        </span>
      </p>
      {job?.state === 'done' &&
        (job.files.length > 0 ? (
          <ul className="file-list">
            {job.files.map((name, index) => (
              <li key={index}>
                <a className="file-link" href={fileUrl(job.id, index)} download>
                  <FileDown size={16} aria-hidden="true" />
                  <span title={name}>{name}</span>
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="download-error">Ningún producto generó archivos.</p>
        ))}
      {failed.length > 0 && (
        <ul className="error-list">
          {failed.map((r) => (
            <li key={r.product_id}>{r.error}</li>
          ))}
        </ul>
      )}
    </>
  )
}

const formatSideKm = (km: number) => `${Number.isInteger(km) ? km : km.toFixed(1)} km`

function DownloadSection({ download, zoneCount }: { download: DownloadController; zoneCount: number }) {
  const { area, params, setDates, togglePol, datesOk, estimate, estimateError, estimating, run, canStart, start } =
    download
  const warnings = estimate ? warningsFor(estimate) : []
  // Until the search fixes the product count, size is for one product.
  const perProduct = run.productCount === null
  // No date after yesterday, the same limit useDownload.setDates enforces.
  const latest = yesterdayIso()
  return (
    <>
      {/* The download covers the square of the selected point of interest, not the study area. */}
      {area ? (
        <p className="download-area" title={area.name}>
          {area.name} · {formatSideKm(area.sideKm)} de lado
        </p>
      ) : (
        <p className="empty-state">
          {zoneCount > 0
            ? 'Selecciona uno de tus puntos de interés (sección «Puntos de interés») para descargar su área.'
            : 'Selecciona un punto de interés para descargar.'}
        </p>
      )}
      {area?.outsideStudy && (
        <div className="download-warning" role="status">
          <TriangleAlert size={16} aria-hidden="true" />
          <div>El punto está fuera del área de estudio</div>
        </div>
      )}

      <div className="field">
        <span className="field-label">Rango de fechas</span>
        <div className="field-row">
          <input
            className="input"
            type="date"
            aria-label="Fecha inicial"
            value={params.start}
            max={params.end && params.end < latest ? params.end : latest}
            onChange={(e) => setDates({ start: e.target.value })}
          />
          <input
            className="input"
            type="date"
            aria-label="Fecha final"
            value={params.end}
            min={params.start || undefined}
            max={latest}
            onChange={(e) => setDates({ end: e.target.value })}
          />
        </div>
        {!datesOk && (
          <p className="download-error">Revisa el rango: la fecha inicial no puede ser posterior a la final.</p>
        )}
      </div>

      <div className="field">
        <span className="field-label" id="download-pol-label">
          Polarización
        </span>
        <div className="segmented" role="group" aria-labelledby="download-pol-label">
          {POLS.map((pol) => {
            const on = params.pols.includes(pol)
            const Icon = on ? Check : Plus
            return (
              <button
                key={pol}
                type="button"
                className={on ? 'active' : undefined}
                aria-pressed={on}
                onClick={() => togglePol(pol)}
              >
                <Icon size={16} aria-hidden="true" />
                {pol}
              </button>
            )
          })}
        </div>
      </div>

      <h3 className="section-title">Estimación</h3>
      <dl className="stat-list" aria-busy={estimating}>
        <dt>Área</dt>
        <dd>{estimate ? formatKm2(estimate.area_km2) : '—'}</dd>
        <dt>{perProduct ? 'Tamaño por producto' : 'Tamaño'}</dt>
        <dd title={estimate?.assumptions}>{estimate?.human ?? '—'}</dd>
        <dt>Productos</dt>
        <dd title={perProduct ? 'Se conoce al buscar; la búsqueda devuelve hasta 10' : undefined}>
          {run.productCount ?? `hasta ${MAX_SEARCH_PRODUCTS}`}
        </dd>
      </dl>
      {estimateError && <p className="download-error">No se pudo estimar: {estimateError}</p>}

      {warnings.length > 0 && (
        <div className="download-warning" role="status">
          <TriangleAlert size={16} aria-hidden="true" />
          <div>
            <strong>Atención</strong>
            <ul>
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <button type="button" className="btn btn-active download-action" disabled={!canStart} onClick={start}>
        <Download size={16} aria-hidden="true" />
        Descargar
      </button>
      <RunStatus run={run} />
      <p className="hint">Harmony procesa cada producto. El estado se consulta cada {POLL_MS / 1000} s.</p>
    </>
  )
}

export default function Sidebar({
  polygons,
  mode,
  regions,
  basemap,
  download,
  cover,
  onSelectMode,
  onDelete,
  onHoverTool,
  onBasemapChange,
  overlays,
  onOverlayChange,
  aoiFill,
  onAoiFill,
  water,
  waterTarget,
  ...zoneProps
}: Props) {
  const [collapsed, setCollapsed] = useState(readStoredCollapsed)
  const [section, setSection] = useState<SectionId>(readStoredSection)

  const toggleCollapsed = () => {
    const next = !collapsed
    setCollapsed(next)
    store(STORAGE_COLLAPSED, next ? '1' : '0')
  }

  const openSection = (id: SectionId) => {
    if (collapsed) {
      setCollapsed(false)
      store(STORAGE_COLLAPSED, '0')
    }
    setSection(id)
    store(STORAGE_SECTION, id)
  }

  const active = SECTIONS.find((s) => s.id === section) ?? SECTIONS[0]

  return (
    <aside className="sidebar" data-collapsed={collapsed} aria-label="Panel de trabajo">
      <nav className="rail" aria-label="Secciones" data-tour="rail">
        {SECTIONS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            className="rail-btn"
            data-tour={`rail-${id}`}
            aria-label={label}
            aria-current={!collapsed && active.id === id ? 'true' : undefined}
            onClick={() => openSection(id)}
          >
            <Icon size={20} aria-hidden="true" />
            <span className="rail-tooltip" aria-hidden="true">
              {label}
            </span>
          </button>
        ))}
        <div className="rail-spacer" />
        <button type="button" className="rail-btn" data-tour="tour-btn" aria-label="Ver guía" onClick={() => startTour()}>
          <Compass size={20} aria-hidden="true" />
          <span className="rail-tooltip" aria-hidden="true">
            Ver guía
          </span>
        </button>
        <button
          type="button"
          className="rail-btn"
          aria-label={collapsed ? 'Expandir panel' : 'Plegar panel'}
          title={collapsed ? 'Expandir panel' : 'Plegar panel'}
          aria-expanded={!collapsed}
          onClick={toggleCollapsed}
        >
          {collapsed ? <PanelLeftOpen size={20} aria-hidden="true" /> : <PanelLeftClose size={20} aria-hidden="true" />}
          <span className="rail-tooltip" aria-hidden="true">
            {collapsed ? 'Expandir' : 'Plegar'}
          </span>
        </button>
      </nav>

      <div className="panel" data-tour="panel" inert={collapsed || undefined} aria-hidden={collapsed}>
        <header className="panel-header">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true" />
            <div className="brand-text">
              <span className="brand-title">Luzsi</span>
              <span className="brand-subtitle">NISAR · NASA Space Apps 2026</span>
            </div>
          </div>
          <button
            type="button"
            className="btn-icon panel-toggle"
            aria-label="Plegar panel"
            title="Plegar panel"
            onClick={toggleCollapsed}
          >
            <PanelLeftClose size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="panel-body">
          <h2 className="panel-section-heading">{active.label}</h2>
          {active.id === 'study' && (
            <StudyAreaSection
              polygons={polygons}
              mode={mode}
              regions={regions}
              onSelectMode={onSelectMode}
              onDelete={onDelete}
              onHoverTool={onHoverTool}
              aoiFill={aoiFill}
              onAoiFill={onAoiFill}
            />
          )}
          {active.id === 'zones' && <ZonesSection {...zoneProps} />}
          {active.id === 'cover' && <CoverSection cover={cover} />}
          {active.id === 'download' && <DownloadSection download={download} zoneCount={zoneProps.zones.length} />}
          {active.id === 'water' && <WaterSection water={water} target={waterTarget} />}
          {active.id === 'layers' && (
            <LayersSection
              basemap={basemap}
              onBasemapChange={onBasemapChange}
              overlays={overlays}
              onOverlayChange={onOverlayChange}
            />
          )}
          {active.id === 'about' && <AboutSection />}
        </div>
      </div>
    </aside>
  )
}
