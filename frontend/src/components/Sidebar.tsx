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
        Fill opacity <span className="layer-pct">{value}%</span>
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
        aria-label="Fill opacity"
        aria-valuetext={`${value}%`}
      />
    </div>
  )
}

const SECTIONS: { id: SectionId; label: string; Icon: LucideIcon }[] = [
  { id: 'study', label: 'Study area', Icon: Pentagon },
  { id: 'zones', label: 'Points of interest', Icon: MapPin },
  { id: 'cover', label: 'Land cover', Icon: Trees },
  { id: 'download', label: 'Download', Icon: Download },
  { id: 'water', label: 'Your model', Icon: Plug },
  { id: 'layers', label: 'Layers', Icon: Layers },
  { id: 'about', label: 'About', Icon: Info },
]

// Shared with the map tool palette so icons and labels are never duplicated.
export const TOOLS: { mode: DrawMode; label: string; Icon: LucideIcon }[] = [
  { mode: 'polygon', label: 'Polygon', Icon: Pentagon },
  { mode: 'rectangle', label: 'Rectangle', Icon: RectangleHorizontal },
  { mode: 'region', label: 'Region', Icon: MapIcon },
]

const HINTS: Record<DrawMode, string> = {
  polygon:
    'Click to add vertices. Double-click, Enter, or click the first vertex to close. Backspace removes the last vertex. Esc cancels.',
  rectangle: 'Click one corner, then the opposite corner. Esc cancels.',
  region: '',
}

const LEVELS: { level: AdminLevel; label: string }[] = [
  { level: 'ADM0', label: 'Country' },
  { level: 'ADM1', label: 'State/Province' },
  { level: 'ADM2', label: 'Municipality' },
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
        Auto level:{' '}
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
            ? 'Click a country to add it.'
            : country
              ? `${country.name}: click a subdivision to add it, or another country to switch.`
              : 'Click a country to see its subdivisions.')}
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
      <h3 className="section-title">Drawing tools</h3>
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
        Study areas
        <span className="count">{polygons.length}</span>
      </h3>
      {polygons.length > 0 ? (
        <ul className="polygon-list">
          {polygons.map((p) => (
            <li key={p.id}>
              <span className="polygon-name">
                {p.name}
                {p.kind === 'polygon' && <small> ({p.coords.length} vertices)</small>}
              </span>
              <button
                type="button"
                className="btn-icon"
                onClick={() => onDelete(p.id)}
                title={`Delete ${p.name}`}
                aria-label={`Delete ${p.name}`}
              >
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-state">No areas yet. Draw a polygon or pick a region.</p>
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
      <h3 className="section-title">Mark</h3>
      <div className="btn-row">
        <button
          type="button"
          className={zonePlacing ? 'btn btn-active' : 'btn'}
          aria-pressed={zonePlacing}
          onClick={onToggleZonePlacing}
        >
          <MapPin size={16} aria-hidden="true" />
          Mark point
        </button>
      </div>
      <p className="hint">
        {zonePlacing
          ? 'Click the map to set the center. Esc cancels.'
          : zones.length
            ? 'Drag a center to move its square, or a corner of the selected one to change its range.'
            : 'Mark points of interest with a square range. They do not change the study area.'}
      </p>

      {zones.length ? (
        <>
          <h3 className="section-title">Points of interest</h3>
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
                    <span className="zone-item-name">{zone.name || `Point ${i + 1}`}</span>
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
        <p className="empty-state">No points yet. Press &quot;Mark point&quot; and click the map.</p>
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
        <span className="field-label">Center</span>
        <span className="zone-coords">
          {zone.center[1].toFixed(5)}, {zone.center[0].toFixed(5)}
        </span>
      </div>
      <div className="field">
        <label className="field-row field-row-label" htmlFor="zone-side">
          <span className="field-label">Range (side)</span>
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
          aria-label="Range"
          aria-valuetext={`${sideKm} km`}
        />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="zone-name">
          Name
        </label>
        <input
          id="zone-name"
          className="input"
          value={zone.name ?? ''}
          placeholder="Optional"
          onChange={(e) => onZoneChange({ ...zone, name: e.target.value || undefined })}
        />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="zone-note">
          Note
        </label>
        <textarea
          id="zone-note"
          className="input zone-note-input"
          rows={2}
          value={zone.note ?? ''}
          placeholder="Optional"
          onChange={(e) => onZoneChange({ ...zone, note: e.target.value || undefined })}
        />
      </div>
      <div className="btn-row">
        <button type="button" className="btn" onClick={() => onFocusZone(zone.id)}>
          <ScanSearch size={16} aria-hidden="true" />
          Go to
        </button>
        <button type="button" className="btn" onClick={() => onDeleteZone(zone.id)}>
          <Trash2 size={16} aria-hidden="true" />
          Delete
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
      <h3 className="section-title">Basemap</h3>
      <div className="option-list" role="radiogroup" aria-label="Basemap">
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
        <span>Water layers</span>
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
              aria-label={`${o.label} opacity`}
              aria-valuetext={`${st.opacity}%`}
            />
            {o.needsDate && (
              <input
                className="input layer-date"
                type="date"
                value={st.date}
                disabled={!st.on}
                onChange={(e) => e.target.value && onOverlayChange(id, { date: e.target.value })}
                aria-label={`${o.label} date`}
              />
            )}
            {(id === 'nisar' || id === 'dswx') && <p className="layer-hint">12-day mosaic up to this date</p>}
            {id === 'nisar' && (
              <div className="layer-sub">
              <label className="layer-check">
                <input
                  type="checkbox"
                  checked={st.outline ?? true}
                  disabled={!st.on}
                  onChange={(e) => onOverlayChange(id, { outline: e.target.checked })}
                />
                <span>Orbit outline</span>
              </label>
              <p className="layer-hint">
                {(st.outline ?? true) ? 'Zoomed out: orbit outline · zoomed in: color mosaic' : 'Mosaic visible when zoomed in'}
              </p>
              </div>
            )}
            {id === 'nisar' && (
              // Orbit pass filter: its own group (it filters both the image and the outline).
              // At least one direction stays on: the last checked box is disabled.
              <div className="layer-sub" role="group" aria-label="NISAR passes">
              <span className="layer-hint">Passes:</span>
              {(
                [
                  ['asc', 'Ascending', NISAR_ASC_COLOR],
                  ['desc', 'Descending', NISAR_DESC_COLOR],
                ] as const
              ).map(([k, label, color]) => {
                const checked = st[k] ?? true
                const other = (k === 'asc' ? st.desc : st.asc) ?? true
                return (
                  <label key={k} className="layer-check" title={checked && !other ? 'At least one pass must stay on' : undefined}>
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
              <p className="layer-hint">Filters image and outline</p>
              </div>
            )}
            {id === 'nisar' && (
              <div className="segmented" role="group" aria-label="NISAR mode">
                {(
                  [
                    ['water', 'Water (threshold)', Droplets],
                    ['color', 'Color (smoothed)', Palette],
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
                <span className="layer-dot layer-dot-sm" style={{ background: '#2b8cbe' }} aria-hidden="true" /> Blue = low L-band backscatter (water/smooth surface)
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

const JOB_LABEL = { queued: 'Queued', running: 'Processing' } as const

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
          min {fmt(stats.min)} · max {fmt(stats.max)} · mean {fmt(stats.mean)}
          {u}
          {stats.fraction != null && output !== 'continuous' && <> · {(stats.fraction * 100).toFixed(1)} % of area</>}
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
    '  "name": "my-model",',
    '  "output": "probability",',
    '  "pols": ["HH"],',
    '  "label": "Water",',
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
  const desc = [model.name ?? 'model', model.label].filter(Boolean).join(' · ')
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
      Connect model
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
      <div className="btn-row">
        <button
          type="button"
          className="btn btn-active"
          disabled={!target || busy}
          title={!target ? 'Pick an area first (max. 60 km)' : busy ? 'A run is in progress' : `Run the built-in water U-Net on ${target.name}`}
          onClick={() => target && water.runBuiltin(target.bbox)}
        >
          {busy ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <Droplets size={16} aria-hidden="true" />}
          Water model
        </button>
      </div>
      <p className={model.connected ? 'model-status on' : 'model-status'} role="status">
        <span className="model-dot" aria-hidden="true" />
        {model.connected ? `Connected: ${desc}` : 'Disconnected'}
      </p>
      {token ? (
        <>
          <div className="model-token-row">
            <code className="model-token" title={token}>{`${token.slice(0, 10)}…${token.slice(-4)}`}</code>
            <CopyButton text={token} label="Copy token" className="model-icon-btn" />
            <button type="button" className="model-icon-btn" onClick={water.regenerate} title="Regenerate token" aria-label="Regenerate token">
              <RefreshCw size={16} aria-hidden="true" />
            </button>
          </div>
          {!model.connected && <p className="hint">Use the guide to connect your model with curl.</p>}
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
          Run model
        </button>
        {state.status !== 'idle' && (
          <button type="button" className="btn" onClick={water.clear}>
            <Trash2 size={16} aria-hidden="true" />
            Remove
          </button>
        )}
      </div>
      <p className="hint">
        {!model.connected ? 'Connect a model to run it.' : target ? <>Area: {target.name}</> : 'Pick an area (max. 60 km).'}
      </p>
      <button type="button" className="btn model-guide-btn" onClick={() => setGuide(true)}>
        <BookOpen size={16} aria-hidden="true" />
        User guide
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
              <h2 id="model-guide-title">User guide</h2>
              <button type="button" className="model-icon-btn" onClick={() => setGuide(false)} title="Close" aria-label="Close" autoFocus>
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <p className="body-text">
              Your model reads <code>input.tif</code> (dB, one band per polarization) and returns a 1-band GeoTIFF.
            </p>
            <ol className="body-text model-steps">
              <li>
                Generate a session token (2 h):
                {token ? <p className="hint">Token ready; the commands already include it.</p> : <div className="btn-row">{connectBtn}</div>}
                {tokenError}
              </li>
              <li className={dim}>
                Introduce your model:
                <CodeBlock code={cmdHello} label="Copy hello command" />
                <p className="hint">
                  <code>output</code>: <code>probability</code> (0–1), <code>continuous</code> or <code>classes</code>.{' '}
                  <code>pols</code>: polarizations it reads (HH, HV, VV, VH).
                </p>
                <details>
                  <summary>Windows PowerShell</summary>
                  <CodeBlock code={cmdHelloPs} label="Copy hello command (PowerShell)" />
                </details>
              </li>
              <li className={dim}>Select an area and press &quot;Run model&quot;.</li>
              <li className={dim}>
                Take the job (returns <code>job_id</code> and <code>input_url</code>):
                <CodeBlock code={cmdNext} label="Copy jobs/next command" />
              </li>
              <li className={dim}>
                Download the image:
                <CodeBlock code={cmdInput} label="Copy download command" />
              </li>
              <li className={dim}>
                Process <code>input.tif</code> with your model → <code>result.tif</code> (same grid, 1 float32 band).
              </li>
              <li className={dim}>
                Upload the result; it appears on the map:
                <CodeBlock code={cmdResult} label="Copy upload command" />
              </li>
            </ol>
            <p className="hint">
              After 30 s of inactivity it becomes Disconnected; repeat hello or jobs/next to reconnect. In Windows PowerShell use{' '}
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
            <span>Ready{state.result.label ? `: ${state.result.label}` : ''}</span>
          </p>
          {state.result.datetime && (
            <p className="hint" title={state.result.scene_id}>
              Scene: {state.result.datetime.slice(0, 10)}
            </p>
          )}
          <ModelLegend result={state.result} />
          <label className="field-label">
            <input type="checkbox" checked={water.visible} onChange={(e) => water.setVisible(e.target.checked)} /> Show
            model result
          </label>
          <div className="field">
            <span className="field-label">
              Opacity <span className="layer-pct">{water.opacity}%</span>
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
              aria-label="Model result opacity"
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
      <h3 className="section-title">What is NISAR?</h3>
      <p className="body-text">
        NISAR is a synthetic aperture radar (SAR) satellite built by NASA and ISRO. It measures
        millimeter-scale changes of the Earth&apos;s surface: wetlands, wildfires, earthquakes, crops, glaciers
        and land subsidence.
      </p>
      <p className="body-text">
        The radar is active: it lights the ground with microwaves and listens for the echo. So it sees day and
        night, and through clouds, smoke and light rain, something an optical sensor cannot do.
      </p>
      <h3 className="section-title">HH vs HV</h3>
      <p className="body-text">
        <strong>HH</strong> transmits and receives in horizontal polarization: sensitive to rough surfaces and
        soil structure. <strong>HV</strong> transmits horizontal and receives vertical: sensitive to vegetation
        volume and biomass. Comparing both separates bare soil from vegetation canopy.
      </p>
      <p className="hint">NASA Space Apps Challenge 2026 · Dancing with the SARs</p>
    </>
  )
}

// Share of each class in the active area. A bar toggles its class in the map filter, shared with the search bar.
function CoverSection({ cover }: { cover: LandcoverController }) {
  const { suggestions, toggle } = cover
  const { area, filter, classesError } = suggestions
  if (!area) return <p className="empty-state">Select or draw an area on the map to see its land cover.</p>
  if (classesError) return <p className="download-error">Error: {classesError}</p>
  const entry = area.stats
  if (entry?.status === 'error') return <p className="download-error">Error: {entry.message}</p>
  if (entry?.status !== 'ready') {
    return (
      <p className="cover-status">
        <Loader2 size={16} className="spin" aria-hidden="true" />
        Loading land cover…
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
                title={on ? `Remove ${c.name} from filter` : `Filter map by ${c.name}`}
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
      <p className="hint">Click a land cover class to filter the map. Resolution {stats.resolution_m} m.</p>
    </>
  )
}

const RUN_STATUS: Record<
  Exclude<RunPhase, 'idle'>,
  { label: string; Icon: LucideIcon; tone: 'busy' | 'ok' | 'error' | 'muted'; spin?: boolean }
> = {
  searching: { label: 'Searching', Icon: Loader2, tone: 'busy', spin: true },
  queued: { label: 'Queued', Icon: Clock, tone: 'busy' },
  running: { label: 'Processing', Icon: Loader2, tone: 'busy', spin: true },
  done: { label: 'Done', Icon: CircleCheck, tone: 'ok' },
  failed: { label: 'Error', Icon: CircleX, tone: 'error' },
  error: { label: 'Error', Icon: CircleX, tone: 'error' },
  empty: { label: 'No NISAR data for this region and dates', Icon: CircleAlert, tone: 'muted' },
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
          <p className="download-error">No product produced files.</p>
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
          {area.name} · {formatSideKm(area.sideKm)} per side
        </p>
      ) : (
        <p className="empty-state">
          {zoneCount > 0
            ? 'Select one of your points of interest (Points of interest section) to download its area.'
            : 'Select a point of interest to download.'}
        </p>
      )}
      {area?.outsideStudy && (
        <div className="download-warning" role="status">
          <TriangleAlert size={16} aria-hidden="true" />
          <div>The point is outside the study area</div>
        </div>
      )}

      <div className="field">
        <span className="field-label">Date range</span>
        <div className="field-row">
          <input
            className="input"
            type="date"
            aria-label="Start date"
            value={params.start}
            max={params.end && params.end < latest ? params.end : latest}
            onChange={(e) => setDates({ start: e.target.value })}
          />
          <input
            className="input"
            type="date"
            aria-label="End date"
            value={params.end}
            min={params.start || undefined}
            max={latest}
            onChange={(e) => setDates({ end: e.target.value })}
          />
        </div>
        {!datesOk && (
          <p className="download-error">Check the range: the start date cannot be after the end date.</p>
        )}
      </div>

      <div className="field">
        <span className="field-label" id="download-pol-label">
          Polarization
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

      <h3 className="section-title">Estimate</h3>
      <dl className="stat-list" aria-busy={estimating}>
        <dt>Area</dt>
        <dd>{estimate ? formatKm2(estimate.area_km2) : '—'}</dd>
        <dt>{perProduct ? 'Size per product' : 'Size'}</dt>
        <dd title={estimate?.assumptions}>{estimate?.human ?? '—'}</dd>
        <dt>Products</dt>
        <dd title={perProduct ? 'Known after searching; search returns up to 10' : undefined}>
          {run.productCount ?? `up to ${MAX_SEARCH_PRODUCTS}`}
        </dd>
      </dl>
      {estimateError && <p className="download-error">Could not estimate: {estimateError}</p>}

      {warnings.length > 0 && (
        <div className="download-warning" role="status">
          <TriangleAlert size={16} aria-hidden="true" />
          <div>
            <strong>Warning</strong>
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
        Download
      </button>
      <RunStatus run={run} />
      <p className="hint">Harmony processes each product. Status is checked every {POLL_MS / 1000} s.</p>
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
    <aside className="sidebar" data-collapsed={collapsed} aria-label="Workspace panel">
      <nav className="rail" aria-label="Sections" data-tour="rail">
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
        <button type="button" className="rail-btn" data-tour="tour-btn" aria-label="Start tour" onClick={() => startTour()}>
          <Compass size={20} aria-hidden="true" />
          <span className="rail-tooltip" aria-hidden="true">
            Start tour
          </span>
        </button>
        <button
          type="button"
          className="rail-btn"
          aria-label={collapsed ? 'Expand panel' : 'Collapse panel'}
          title={collapsed ? 'Expand panel' : 'Collapse panel'}
          aria-expanded={!collapsed}
          onClick={toggleCollapsed}
        >
          {collapsed ? <PanelLeftOpen size={20} aria-hidden="true" /> : <PanelLeftClose size={20} aria-hidden="true" />}
          <span className="rail-tooltip" aria-hidden="true">
            {collapsed ? 'Expand' : 'Collapse'}
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
            aria-label="Collapse panel"
            title="Collapse panel"
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
