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
    title: 'Study area',
    description: 'Draw a polygon or rectangle, or pick a country or subdivision on the map. It sets where data is analyzed.',
  },
  {
    id: 'zones',
    title: 'Points of interest',
    description: 'Mark points with an adjustable square range, a name and a note. Use them to download data and run models.',
  },
  {
    id: 'cover',
    title: 'Land cover',
    description: 'Shows the share of each land cover type in the active area. Click one to filter the map.',
  },
  {
    id: 'download',
    title: 'Download',
    description: 'Download NISAR products for the selected point of interest. Pick dates and polarization, check the estimate and download.',
  },
  {
    id: 'water',
    title: 'Your model',
    description: 'Press Connect model and follow the usage guide to send results with curl.',
  },
  {
    id: 'layers',
    title: 'Layers',
    description: 'Change the basemap and turn on water layers: OPERA DSWx, NISAR GCOV and JRC. Adjust date, passes, mode and opacity.',
  },
  {
    id: 'about',
    title: 'About',
    description: 'What NISAR is and how HH and HV polarizations differ.',
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
        title: 'Welcome to Luzsi',
        description:
          'Explore changes on the Earth surface with NISAR radar data (NASA-ISRO). Here are the basics in one minute.',
      },
    },
    {
      element: q('search'),
      popover: {
        title: 'Search and dates',
        description:
          'Search a country, region or natural place and add it as a study area. Pick the date range to analyze here.',
        side: 'bottom',
      },
    },
    {
      element: q('rail'),
      popover: {
        title: 'Tools',
        description: 'This bar opens each panel section. Let us go through them one by one.',
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
        title: 'Timeline',
        description:
          'With an area set, NISAR passes show up here. Pick a date or press play to see the animation.',
        side: 'top',
      },
    },
    {
      element: q('map'),
      popover: {
        title: 'The map',
        description:
          'Click to select areas and points; right-click for more options. Drag and scroll to move around.',
        side: 'left',
        align: 'center',
      },
    },
    {
      element: q('tour-btn'),
      popover: {
        title: 'All set!',
        description: 'You can replay this guide anytime with this button.',
        side: 'right',
      },
    },
  ]
}

export function startTour() {
  const d = driver({
    showProgress: true,
    progressText: '{{current}} of {{total}}',
    nextBtnText: 'Next',
    prevBtnText: 'Back',
    doneBtnText: 'Done',
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
