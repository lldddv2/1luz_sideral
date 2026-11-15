import { driver } from 'driver.js'
import type { Driver, DriveStep } from 'driver.js'
import 'driver.js/dist/driver.css'

// Onboarding tour. Elements are targeted through data-tour attributes.
const SEEN_KEY = 'tour-seen-v2'

const q = (name: string) => `[data-tour="${name}"]`

// One step per sidebar section, in rail order. Descriptions follow what each section actually does.
const SECTION_STEPS: { id: string; title: string; description: string }[] = [
  {
    id: 'study',
    title: 'Área de estudio',
    description: 'Dibuja un polígono o rectángulo, o elige un país o subdivisión en el mapa. Define dónde se analizan los datos.',
  },
  {
    id: 'zones',
    title: 'Puntos de interés',
    description: 'Marca puntos con un rango cuadrado ajustable, con nombre y nota. Sirven para descargar y detectar agua.',
  },
  {
    id: 'cover',
    title: 'Coberturas',
    description: 'Muestra el porcentaje de cada tipo de cobertura del área activa. Haz clic en una para filtrar el mapa.',
  },
  {
    id: 'download',
    title: 'Descarga',
    description: 'Descarga productos NISAR del punto de interés seleccionado. Elige fechas y polarización, revisa la estimación y descarga.',
  },
  {
    id: 'water',
    title: 'Agua (U-Net)',
    description: 'Detecta agua con un modelo U-Net sobre la escena NISAR HH más reciente del área. Muestra el mapa de probabilidad.',
  },
  {
    id: 'layers',
    title: 'Capas',
    description: 'Cambia el mapa base y activa capas de agua: OPERA DSWx, NISAR GCOV y JRC. Ajusta fecha, pasadas, modo y opacidad.',
  },
  {
    id: 'about',
    title: 'Acerca',
    description: 'Qué es NISAR y en qué se diferencian las polarizaciones HH y HV.',
  },
]

// Opens a sidebar section by clicking its rail button, then advances once React has rendered it.
function openSectionThen(id: string, d: Driver, dir: 'next' | 'prev') {
  const btn = document.querySelector<HTMLButtonElement>(q(`rail-${id}`))
  // Skip the click when already open, in case the rail ever becomes a toggle.
  if (btn && btn.getAttribute('aria-current') !== 'true') btn.click()
  requestAnimationFrame(() => requestAnimationFrame(() => (dir === 'next' ? d.moveNext() : d.movePrevious())))
}

function steps(): DriveStep[] {
  return [
    {
      popover: {
        title: 'Bienvenido a Luzsi',
        description:
          'Explora cambios en la superficie terrestre con datos de radar NISAR (NASA-ISRO). Te mostramos lo básico en un minuto.',
      },
    },
    {
      element: q('search'),
      popover: {
        title: 'Buscar y fechas',
        description:
          'Busca un país, región o lugar natural y añádelo como área de estudio. Elige aquí el rango de fechas a analizar.',
        side: 'bottom',
      },
    },
    {
      element: q('rail'),
      popover: {
        title: 'Herramientas',
        description: 'Esta barra abre cada sección del panel. Veámoslas una por una.',
        side: 'right',
        onNextClick: (_el, _step, { driver: d }) => openSectionThen(SECTION_STEPS[0].id, d, 'next'),
      },
    },
    ...SECTION_STEPS.map((s, i): DriveStep => {
      const prev = SECTION_STEPS[i - 1]
      const next = SECTION_STEPS[i + 1]
      return {
        element: q('panel'),
        popover: {
          title: s.title,
          description: s.description,
          side: 'right',
          ...(prev && { onPrevClick: (_el, _step, { driver: d }) => openSectionThen(prev.id, d, 'prev') }),
          ...(next && { onNextClick: (_el, _step, { driver: d }) => openSectionThen(next.id, d, 'next') }),
        },
      }
    }),
    {
      element: q('timeline'),
      popover: {
        title: 'Línea de tiempo',
        description:
          'Con un área definida aparecen aquí las pasadas NISAR. Elige una fecha o pulsa reproducir para ver la animación.',
        side: 'top',
      },
    },
    {
      element: q('map'),
      popover: {
        title: 'El mapa',
        description:
          'Haz clic para seleccionar áreas y puntos; usa clic derecho para más opciones. Arrastra y usa la rueda para moverte.',
        side: 'left',
        align: 'center',
      },
    },
    {
      element: q('tour-btn'),
      popover: {
        title: '¡Listo!',
        description: 'Puedes volver a ver esta guía cuando quieras con este botón.',
        side: 'right',
      },
    },
  ]
}

export function startTour() {
  const d = driver({
    showProgress: true,
    progressText: '{{current}} de {{total}}',
    nextBtnText: 'Siguiente',
    prevBtnText: 'Anterior',
    doneBtnText: 'Listo',
    overlayOpacity: 0.6,
    popoverClass: 'tour-popover',
    steps: steps(),
  })
  d.drive()
}

export function autoStartTour() {
  try {
    if (localStorage.getItem(SEEN_KEY)) return
  } catch {
    return
  }
  // Let the map and panels mount first. Mark as seen only when it actually starts (StrictMode runs effects twice).
  const t = setTimeout(() => {
    try {
      localStorage.setItem(SEEN_KEY, '1')
    } catch {
      /* ignore */
    }
    startTour()
  }, 800)
  return () => clearTimeout(t)
}
