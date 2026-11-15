import { useEffect, useMemo, useRef, useState } from "react";
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
} from "react";
import { ChevronDown, ChevronLeft, ChevronRight, GitCompare, X } from "lucide-react";
import type { Feature, Point } from "geojson";
import { POI_COLOR, POI_LABEL } from "../pois";
import type { PoiPol, PoiProps } from "../pois";

interface Props {
  poi: Feature<Point, PoiProps>;
  start: string; // search range, YYYY-MM-DD (useDownload params)
  end: string;
  onClose: () => void;
}

const DAY_MS = 86400000;
const dayOf = (iso: string) =>
  Math.round(Date.parse(`${iso}T00:00:00Z`) / DAY_MS); // UTC day number
const fmtDay = (day: number) =>
  new Date(day * DAY_MS).toLocaleDateString("es", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
const fmtDb = (v: number) =>
  `${v.toLocaleString("es", { signDisplay: "always", minimumFractionDigits: 1, maximumFractionDigits: 1 })} dB`;
const clamp = (v: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, v));

// NISAR L-band quad-pol: transmit/receive polarization.
const POLS: { code: PoiPol; desc: string }[] = [
  { code: "HH", desc: "horizontal/horizontal" },
  { code: "HV", desc: "horizontal/vertical" },
  { code: "VH", desc: "vertical/horizontal" },
  { code: "VV", desc: "vertical/vertical" },
];
const REPEAT_DAYS = 12; // NISAR repeat cycle, spacing of the mock frames

function hashId(id: string) {
  let h = 7;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h;
}

// mulberry32: small seeded PRNG, so the mock frames are the same on every open.
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Mock SAR frame: smooth backscatter field + 4-look speckle, grayscale, as a data URL.
// `gain` (linear) scales one patch of the scene; 1 = no change.
function sarFrame(poiSeed: number, frameSeed: number, gain: number): string {
  const W = 240;
  const H = 160;
  const terrain = rng(poiSeed);
  const blobs = Array.from({ length: 5 }, () => ({
    x: terrain() * W,
    y: terrain() * H,
    r: (0.12 + terrain() * 0.2) * W,
    a: 0.15 + terrain() * 0.35,
  }));
  const patch = {
    x: W * (0.35 + terrain() * 0.3),
    y: H * (0.35 + terrain() * 0.3),
    r: 0.22 * W,
  };
  const speckle = rng(frameSeed);
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  const img = ctx.createImageData(W, H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      let v = 0.3;
      for (const b of blobs)
        v += b.a * Math.exp(-((x - b.x) ** 2 + (y - b.y) ** 2) / (b.r * b.r));
      const dp =
        ((x - patch.x) ** 2 + (y - patch.y) ** 2) / (patch.r * patch.r);
      const field = v * (1 + (gain - 1) * Math.exp(-dp));
      let s = 0;
      for (let k = 0; k < 4; k++) s -= Math.log(Math.max(speckle(), 1e-6)) / 4;
      const g = Math.pow(Math.min(1, field * s * 0.7), 0.9) * 255;
      img.data.set([g, g, g, 255], (y * W + x) * 4);
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL();
}

// Mock acquisition days: one every REPEAT_DAYS across [lo, hi], with the grid
// aligned so the POI date is exactly one frame. A range too short for two
// frames falls back to [lo, hi].
// TODO: once the backend is wired, replace this with the acquisition dates the API returns.
function frameDays(eventDay: number, lo: number, hi: number): number[] {
  const first = eventDay + Math.ceil((lo - eventDay) / REPEAT_DAYS) * REPEAT_DAYS;
  const days: number[] = [];
  for (let d = first; d <= hi; d += REPEAT_DAYS) days.push(d);
  return days.length >= 2 ? days : [lo, hi];
}

const MAX_TICKS = 100; // above this, ticks blur into the bar; draw only the active mark

export default function PoiPanel({ poi, start, end, onClose }: Props) {
  const p = poi.properties;
  const color = POI_COLOR[p.category];

  // Guard against an inverted or invalid range from the date inputs.
  const lo = Number.isFinite(dayOf(start)) ? dayOf(start) : dayOf(p.date);
  const hiRaw = Number.isFinite(dayOf(end)) ? dayOf(end) : lo;
  const hi = Math.max(hiRaw, lo + 1);
  const eventDay = dayOf(p.date);
  const pctOf = (day: number) => clamp(((day - lo) / (hi - lo)) * 100, 0, 100);

  const frames = useMemo(
    () => frameDays(eventDay, lo, hi).map((day) => ({ day })),
    [lo, hi, eventDay],
  );
  const n = frames.length;

  const nearestIndex = (day: number) => {
    let best = 0;
    for (let i = 1; i < n; i++)
      if (Math.abs(frames[i].day - day) < Math.abs(frames[best].day - day))
        best = i;
    return best;
  };

  const [active, setActive] = useState(() => nearestIndex(eventDay));
  const [pol, setPol] = useState<PoiPol>("HH");
  const [tip, setTip] = useState<{ x: number; day: number } | null>(null);

  const plotRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef(false);

  // Reset when frames change (new POI or new range): open on the frame of the POI date.
  useEffect(() => {
    setActive(nearestIndex(eventDay));
    // Only frames matter here; eventDay changes together with them.
  }, [frames]);

  const goTo = (k: number) => setActive(k);

  // Images are generated lazily, only for the frame on screen, and cached by day.
  // The seed depends on (POI, day), so a given day always renders the same image.
  const srcCache = useRef(new Map<number, string>());
  const cacheKey = useRef("");
  const key = `${p.id}|${p.change_db}|${lo}|${hi}`;
  if (cacheKey.current !== key) {
    // Clear synchronously so a new POI never reads the previous POI's images.
    cacheKey.current = key;
    srcCache.current = new Map();
  }
  const activeDay = frames[active]?.day;
  const activeSrc = useMemo(() => {
    if (activeDay === undefined) return "";
    const cached = srcCache.current.get(activeDay);
    if (cached !== undefined) return cached;
    const seed = hashId(p.id);
    const gain = 10 ** (p.change_db / 10); // mock change, applied from the POI date on
    const src = sarFrame(
      seed,
      (Math.imul(seed, 31) + activeDay) >>> 0,
      activeDay >= eventDay ? gain : 1,
    );
    srcCache.current.set(activeDay, src);
    return src;
  }, [activeDay, p.id, p.change_db, eventDay]);

  const fractionAt = (clientX: number) => {
    const rect = plotRef.current!.getBoundingClientRect();
    return {
      f: clamp((clientX - rect.left) / rect.width, 0, 1),
      width: rect.width,
    };
  };
  const pickAt = (clientX: number) =>
    goTo(nearestIndex(lo + fractionAt(clientX).f * (hi - lo)));
  const showTip = (clientX: number) => {
    const { f, width } = fractionAt(clientX);
    setTip({
      x: clamp(f * width, 30, width - 30),
      day: Math.round(lo + f * (hi - lo)),
    });
  };

  const onPlotDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    e.currentTarget.focus({ preventScroll: true });
    dragRef.current = true;
    pickAt(e.clientX);
    showTip(e.clientX);
  };
  const onPlotMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    showTip(e.clientX);
    if (dragRef.current) pickAt(e.clientX);
  };
  const onPlotKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = {
      ArrowRight: active + 1,
      ArrowUp: active + 1,
      ArrowLeft: active - 1,
      ArrowDown: active - 1,
      Home: 0,
      End: n - 1,
    };
    if (!(e.key in moves)) return;
    e.preventDefault();
    goTo(clamp(moves[e.key], 0, n - 1));
  };

  const rows: [string, string][] = [
    ["Fecha", p.date],
    ["Cambio (log-ratio)", fmtDb(p.change_db)],
    ...(["HH", "HV"] as const)
      .filter((k) => p.pol[k] !== undefined)
      .map((k): [string, string] => [`Δ ${k}`, fmtDb(p.pol[k]!)]),
  ];

  return (
    <section className="poi-panel" aria-label={`Detalle: ${p.name}`}>
      <div className="poi-body">
        <div className="poi-left">
          <div className="poi-frame">
            {frames[active] && (
              <>
                <img
                  src={activeSrc}
                  alt={`Imagen de ejemplo, ${fmtDay(frames[active].day)}`}
                  draggable={false}
                />
                <span className="poi-frame-date">
                  {fmtDay(frames[active].day)}
                </span>
                <button
                  type="button"
                  className="poi-frame-nav prev"
                  title="Imagen anterior"
                  aria-label="Imagen anterior"
                  disabled={active <= 0}
                  onClick={() => goTo(active - 1)}
                >
                  <ChevronLeft size={16} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className="poi-frame-nav next"
                  title="Imagen siguiente"
                  aria-label="Imagen siguiente"
                  disabled={active >= n - 1}
                  onClick={() => goTo(active + 1)}
                >
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </>
            )}
          </div>

          <div className="poi-tl">
            <div className="poi-tl-head">
              <span>Línea de tiempo</span>
              <output className="poi-tl-read">
                {fmtDay(frames[active]?.day ?? eventDay)}
              </output>
            </div>
            <div
              ref={plotRef}
              className="poi-tl-plot"
              tabIndex={0}
              role="slider"
              aria-label="Fecha de la imagen"
              aria-valuemin={0}
              aria-valuemax={n - 1}
              aria-valuenow={active}
              aria-valuetext={fmtDay(frames[active]?.day ?? eventDay)}
              onPointerDown={onPlotDown}
              onPointerMove={onPlotMove}
              onPointerUp={() => (dragRef.current = false)}
              onPointerCancel={() => (dragRef.current = false)}
              onPointerLeave={() => !dragRef.current && setTip(null)}
              onKeyDown={onPlotKey}
            >
              <div className="poi-tl-bar" />
              {eventDay >= lo && eventDay <= hi && (
                <span
                  className="poi-tl-event"
                  style={{ left: `${pctOf(eventDay)}%`, background: color }}
                  title={`Fecha del evento: ${fmtDay(eventDay)}`}
                />
              )}
              {n <= MAX_TICKS
                ? frames.map((f, i) => (
                    <span
                      key={f.day}
                      className={`poi-tl-dot${i === active ? " active" : ""}`}
                      style={{ left: `${pctOf(f.day)}%` }}
                    />
                  ))
                : activeDay !== undefined && (
                    <span
                      className="poi-tl-dot active"
                      style={{ left: `${pctOf(activeDay)}%` }}
                    />
                  )}
              {tip && (
                <div className="poi-tl-tip" style={{ left: tip.x }}>
                  {fmtDay(tip.day)}
                </div>
              )}
            </div>
            <div className="poi-tl-axis">
              <span>{fmtDay(lo)}</span>
              <span>{fmtDay(hi)}</span>
            </div>
          </div>
        </div>

        <div className="poi-right">
          <div className="poi-head">
            <span className="poi-chip">
              <i style={{ background: color }} />
              {POI_LABEL[p.category]}
            </span>
            <button
              type="button"
              className="poi-close"
              title="Cerrar"
              aria-label="Cerrar"
              onClick={onClose}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>
          <h3>{p.name}</h3>

          <div className="poi-pol">
            <label className="poi-pol-label" htmlFor={`poi-pol-${p.id}`}>
              Polarización
            </label>
            <div className="poi-select">
              <select
                id={`poi-pol-${p.id}`}
                value={pol}
                // TODO: wire to polarization layer. Visual selection only for now.
                onChange={(e) => setPol(e.target.value as PoiPol)}
              >
                {POLS.map(({ code, desc }) => (
                  <option key={code} value={code}>
                    {code} — {desc}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} aria-hidden="true" />
            </div>
            <div className="btn-row poi-compare">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  // TODO: open comparison view
                }}
              >
                <GitCompare size={16} aria-hidden="true" />
                Comparar
              </button>
            </div>
          </div>

          <dl>
            {rows.map(([k, v]) => (
              <div key={k} className="poi-row">
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          <p className="poi-src">Fuente: {p.source} · valores de ejemplo</p>
        </div>
      </div>
    </section>
  );
}
