import { useEffect, useRef, useState } from 'react'
import { findCountryAt, loadCountries, loadSubdivisions } from './regions'
import type { AdminLevel, RegionCollection } from './regions'

// Zoom thresholds for the automatic admin level (MapLibre zoom).
// zoom < ADM1_MIN_ZOOM: countries (ADM0); zoom < ADM2_MIN_ZOOM: ADM1; otherwise: ADM2.
const ADM1_MIN_ZOOM = 5
const ADM2_MIN_ZOOM = 8

// Map camera as reported by MapView. center is [lng, lat].
export interface MapViewport {
  zoom: number
  center: [number, number]
}

const levelAt = (zoom: number): AdminLevel =>
  zoom >= ADM2_MIN_ZOOM ? 'ADM2' : zoom >= ADM1_MIN_ZOOM ? 'ADM1' : 'ADM0'

export interface RegionPicker {
  level: AdminLevel
  zoom: number
  countries: RegionCollection | null
  subdivisions: RegionCollection | null
  country: { iso: string; name: string } | null
  status: string | null
  pickCountry: (iso: string, name: string) => void
}

// State for picking countries / subdivisions while the "region" tool is active.
// The level follows the map zoom; below ADM0 the country under the map center is selected.
export function useRegionPicker(active: boolean, view: MapViewport): RegionPicker {
  const level = levelAt(view.zoom)
  const [countries, setCountries] = useState<RegionCollection | null>(null)
  const [subdivisions, setSubdivisions] = useState<RegionCollection | null>(null)
  const [country, setCountry] = useState<{ iso: string; name: string } | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const request = useRef('')

  useEffect(() => {
    if (!active || countries) return
    setStatus('Loading countries…')
    loadCountries().then(
      (fc) => {
        setCountries(fc)
        setStatus(null)
      },
      () => setStatus('Could not load countries. Check your connection.'),
    )
  }, [active, countries])

  // (Re)load subdivisions when the country or level changes while the tool is active.
  useEffect(() => {
    setSubdivisions(null)
    if (!active || !country || level === 'ADM0') {
      request.current = ''
      // Drop a message left by a request that no longer applies (e.g. zoomed out mid-load).
      if (country) setStatus(null)
      return
    }
    const key = `${country.iso}/${level}`
    request.current = key
    setStatus(`Loading subdivisions of ${country.name}…`)
    loadSubdivisions(country.iso, level).then(
      (fc) => {
        if (request.current !== key) return
        setSubdivisions(fc)
        setStatus(null)
      },
      () => {
        if (request.current !== key) return
        setStatus(`No ${level} boundaries available for ${country.name}.`)
      },
    )
  }, [active, country, level])

  const pickCountry = (iso: string, name: string) => {
    if (country?.iso !== iso) setCountry({ iso, name })
  }

  // Prefetch the next level so it is cached before the user zooms in. State stays untouched.
  useEffect(() => {
    if (!active || !countries) return
    const next: Exclude<AdminLevel, 'ADM0'> | null =
      view.zoom >= ADM2_MIN_ZOOM - 1 ? 'ADM2' : view.zoom >= ADM1_MIN_ZOOM - 1 ? 'ADM1' : null
    if (!next || next === level) return
    // At zoom 4..5 the active country is not resolved yet, so look under the map center.
    const iso = country?.iso ?? findCountryAt(countries, view.center)?.properties.iso
    if (!iso) return
    loadSubdivisions(iso, next).catch(() => {})
  }, [active, countries, level, country, view])

  // Below ADM0, the country under the map center becomes the active country.
  useEffect(() => {
    if (!active || !countries || level === 'ADM0') return
    const hit = findCountryAt(countries, view.center)
    if (hit) pickCountry(hit.properties.iso, hit.properties.name)
  }, [active, countries, level, view])

  return { level, zoom: view.zoom, countries, subdivisions, country, status, pickCountry }
}
