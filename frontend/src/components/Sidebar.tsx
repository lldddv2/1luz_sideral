import { useState } from 'react'
import {
  Activity,
  Info,
  Layers,
  Map as MapIcon,
  PanelLeftClose,
  PanelLeftOpen,
  Pentagon,
  RectangleHorizontal,
  Satellite,
  Trash2,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AoiPolygon, DrawMode } from '../types'
import type { AdminLevel } from '../regions'
import type { RegionPicker } from '../useRegionPicker'
import { BASEMAPS } from '../basemaps'
import type { BasemapId } from '../basemaps'

type SectionId = 'study' | 'nisar' | 'layers' | 'analysis' | 'about'

interface Props {
  polygons: AoiPolygon[]
  mode: DrawMode | null
  regions: RegionPicker
  basemap: BasemapId
  onSelectMode: (mode: DrawMode) => void
  onDelete: (id: string) => void
  onHoverTool: (tool: DrawMode | null) => void
  onBasemapChange: (basemap: BasemapId) => void
}

const SECTIONS: { id: SectionId; label: string; Icon: LucideIcon }[] = [
  { id: 'study', label: 'Área de estudio', Icon: Pentagon },
  { id: 'nisar', label: 'Datos NISAR', Icon: Satellite },
  { id: 'layers', label: 'Capas', Icon: Layers },
  { id: 'analysis', label: 'Análisis', Icon: Activity },
  { id: 'about', label: 'Acerca', Icon: Info },
]

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
          <input id="nisar-start" className="input" type="date" disabled aria-label="Fecha inicial" />
          <input className="input" type="date" disabled aria-label="Fecha final" />
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
}: Pick<Props, 'basemap' | 'onBasemapChange'>) {
  const [opacity, setOpacity] = useState(70)
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

      <h3 className="section-title">Opacidad de capas de radar</h3>
      <div className="field">
        <div className="field-row field-row-label">
          <label className="field-label" htmlFor="radar-opacity">
            Opacidad
          </label>
          <span className="field-value">{opacity}%</span>
        </div>
        <input
          id="radar-opacity"
          className="slider"
          type="range"
          min={0}
          max={100}
          step={5}
          value={opacity}
          onChange={(e) => setOpacity(Number(e.target.value))}
          aria-valuetext={`${opacity}%`}
        />
      </div>
      <p className="hint">Aún no hay capas de radar cargadas; el valor se aplicará cuando existan.</p>
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

export default function Sidebar({
  polygons,
  mode,
  regions,
  basemap,
  onSelectMode,
  onDelete,
  onHoverTool,
  onBasemapChange,
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

  const active = SECTIONS.find((s) => s.id === section)!

  return (
    <aside className="sidebar" data-collapsed={collapsed} aria-label="Panel de trabajo">
      <nav className="rail" aria-label="Secciones">
        {SECTIONS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            className="rail-btn"
            aria-label={label}
            aria-current={!collapsed && section === id ? 'true' : undefined}
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
          {section === 'study' && (
            <StudyAreaSection
              polygons={polygons}
              mode={mode}
              regions={regions}
              onSelectMode={onSelectMode}
              onDelete={onDelete}
              onHoverTool={onHoverTool}
            />
          )}
          {section === 'nisar' && <NisarSection />}
          {section === 'layers' && <LayersSection basemap={basemap} onBasemapChange={onBasemapChange} />}
          {section === 'analysis' && <AnalysisSection />}
          {section === 'about' && <AboutSection />}
        </div>
      </div>
    </aside>
  )
}
