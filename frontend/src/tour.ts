import { driver } from 'driver.js'
import type { Driver, DriveStep } from 'driver.js'
import 'driver.js/dist/driver.css'

// Onboarding tour. Elements are targeted through data-tour attributes.
const SEEN_KEY = 'tour-seen-v1'

const q = (name: string) => `[data-tour="${name}"]`

// Opens a sidebar section by clicking its rail button, then advances once React has rendered it.
function openSectionThen(id: string, d: Driver, dir: 'next' | 'prev') {
  document.querySelector<HTMLButtonElement>(q(`rail-${id}`))?.click()
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
        description:
          'Dibuja áreas, marca puntos de interés, filtra coberturas, descarga productos, detecta agua y consulta información.',
        side: 'right',
        onNextClick: (_el, _step, { driver: d }) => openSectionThen('layers', d, 'next'),
      },
    },
    {
      element: q('panel'),
      popover: {
        title: 'Capas',
        description:
          'Cambia el mapa base y activa capas: agua OPERA DSWx y radar NISAR GCOV. Ajusta polarización, color y opacidad.',
        side: 'right',
      },
    },
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
