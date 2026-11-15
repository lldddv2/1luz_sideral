import { useState } from 'react'
import type { CSSProperties } from 'react'
import {
  Activity,
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
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Pentagon,
  Plus,
  RectangleHorizontal,
  Satellite,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AoiPolygon, DrawMode } from '../types'
import type { AdminLevel } from '../regions'
import type { RegionPicker } from '../useRegionPicker'
import type { DownloadController, RunPhase, RunState } from '../useDownload'
import { MAX_SEARCH_PRODUCTS, POLL_MS, POLS, fileUrl, formatKm2, warningsFor, yesterdayIso } from '../download'
import { BASEMAPS } from '../basemaps'
import type { BasemapId } from '../basemaps'
import { NISAR_ASC_COLOR, NISAR_DESC_COLOR, OVERLAYS, OVERLAY_IDS } from '../layers'
import type { OverlayId, OverlayState } from '../layers'

// Legend color per water layer, shown as a dot next to its name.
const LAYER_DOT: Record<OverlayId, string> = { dswx: '#1f78b4', nisar: '#7b3fbf', jrc: '#14a3a3' }

type SectionId = 'study' | 'download' | 'nisar' | 'layers' | 'analysis' | 'about'

interface Props {
  polygons: AoiPolygon[]
  mode: DrawMode | null
  regions: RegionPicker
  download: DownloadController
  basemap: BasemapId
  onSelectMode: (mode: DrawMode) => void
  onDelete: (id: string) => void
  onHoverTool: (tool: DrawMode | null) => void
  onBasemapChange: (basemap: BasemapId) => void
  overlays: Record<OverlayId, OverlayState>
  onOverlayChange: (id: OverlayId, patch: Partial<OverlayState>) => void
}

const SECTIONS: { id: SectionId; label: string; Icon: LucideIcon }[] = [
  { id: 'study', label: 'Área de estudio', Icon: Pentagon },
  { id: 'download', label: 'Descarga', Icon: Download },
  { id: 'nisar', label: 'Datos NISAR', Icon: Satellite },
  { id: 'layers', label: 'Capas', Icon: Layers },
  { id: 'analysis', label: 'Análisis', Icon: Activity },
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
}: Pick<Props, 'polygons' | 'mode' | 'regions' | 'onSelectMode' | 'onDelete' | 'onHoverTool'>) {
  return (
    <>
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

function NisarSection() {
  const [polarization, setPolarization] = useState<'HH' | 'HV'>('HH')
  return (
    <>
      <div className="section-head">
        <h3 className="section-title">Consulta</h3>
        <span className="badge">Próximamente</span>
      </div>
      <div className="field">
        <label className="field-label" htmlFor="nisar-product">
          Producto
        </label>
        <input id="nisar-product" className="input" value="GCOV (Geocoded Complex)" readOnly disabled />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="nisar-start">
          Rango de fechas
        </label>
        <div className="field-row">
          <input
            id="nisar-start"
            className="input"
            type="date"
            disabled
            aria-label="Fecha inicial"
            max={yesterdayIso()}
          />
          <input className="input" type="date" disabled aria-label="Fecha final" max={yesterdayIso()} />
        </div>
      </div>
      <div className="field">
        <span className="field-label" id="nisar-pol-label">
          Polarización
        </span>
        <div className="segmented" role="group" aria-labelledby="nisar-pol-label">
          <button
            type="button"
            className={polarization === 'HH' ? 'active' : undefined}
            aria-pressed={polarization === 'HH'}
            onClick={() => setPolarization('HH')}
          >
            HH
          </button>
          <button
            type="button"
            className={polarization === 'HV' ? 'active' : undefined}
            aria-pressed={polarization === 'HV'}
            onClick={() => setPolarization('HV')}
          >
            HV
          </button>
        </div>
      </div>
      <p className="hint">
        La descarga y el procesamiento de escenas NISAR todavía no están conectados. Por ahora esta sección
        solo prepara la interfaz.
      </p>
    </>
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

function AnalysisSection() {
  return (
    <>
      <div className="section-head">
        <h3 className="section-title">Serie temporal</h3>
        <span className="badge">Próximamente</span>
      </div>
      <div className="placeholder">
        <Activity size={20} aria-hidden="true" />
        <p>
          Aquí aparecerán las gráficas de la serie temporal del área seleccionada: retrodispersión por fecha,
          coherencia interferométrica y detección de cambios.
        </p>
      </div>
      <p className="hint">Depende de la descarga de escenas NISAR.</p>
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

function DownloadSection({ download }: { download: DownloadController }) {
  const { area, params, setDates, togglePol, datesOk, estimate, estimateError, estimating, run, canStart, start } =
    download
  const warnings = estimate ? warningsFor(estimate) : []
  // Until the search fixes the product count, size is for one product.
  const perProduct = run.productCount === null
  // No date after yesterday, the same limit useDownload.setDates enforces.
  const latest = yesterdayIso()
  return (
    <>
      {area ? (
        <p className="download-area" title={area.name}>
          {area.name}
        </p>
      ) : (
        <p className="empty-state">Selecciona o dibuja un área en el mapa para estimar y descargar datos.</p>
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
  onSelectMode,
  onDelete,
  onHoverTool,
  onBasemapChange,
  overlays,
  onOverlayChange,
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
      <nav className="rail" aria-label="Secciones">
        {SECTIONS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            className="rail-btn"
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

      <div className="panel" inert={collapsed || undefined} aria-hidden={collapsed}>
        <header className="panel-header">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true" />
            <div className="brand-text">
              <span className="brand-title">1luz sideral</span>
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
            />
          )}
          {active.id === 'download' && <DownloadSection download={download} />}
          {active.id === 'nisar' && <NisarSection />}
          {active.id === 'layers' && (
            <LayersSection
              basemap={basemap}
              onBasemapChange={onBasemapChange}
              overlays={overlays}
              onOverlayChange={onOverlayChange}
            />
          )}
          {active.id === 'analysis' && <AnalysisSection />}
          {active.id === 'about' && <AboutSection />}
        </div>
      </div>
    </aside>
  )
}
