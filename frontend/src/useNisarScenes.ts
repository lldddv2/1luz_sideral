import { useEffect, useState } from 'react'
import { shapeGeometry } from './geo'
import { defaultScene, fetchNisarOverlay, fetchNisarScenes } from './nisarScenes'
import type { DateRange } from './passes'
import type { AoiPolygon, NisarOverlay, NisarPol, NisarScene } from './types'

// NISAR scenes in S3 (/api/scenes, source "nisar") over the active area and range, plus the PNG overlay of the
// picked scene. Errors (501 without bucket, 502 S3 down) leave the list empty and do not disturb other flows.
export function useNisarScenes(active: AoiPolygon | null, range: DateRange | null) {
  const [scenes, setScenes] = useState<NisarScene[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [pol, setPol] = useState<NisarPol>('HH')
  const [opacity, setOpacity] = useState(0.85)
  const [overlay, setOverlay] = useState<NisarOverlay | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setScenes([])
    setSelected(null)
    if (!active || !range) return
    const controller = new AbortController()
    fetchNisarScenes(shapeGeometry(active), range, controller.signal).then(
      (list) => {
        setScenes(list)
        setSelected(defaultScene(list)?.scene_id ?? null)
      },
      () => {},
    )
    return () => controller.abort()
  }, [active, range])

  useEffect(() => {
    setOverlay(null)
    if (!active || !selected) return
    const controller = new AbortController()
    let url: string | null = null
    setLoading(true)
    fetchNisarOverlay(selected, shapeGeometry(active), pol, controller.signal)
      .then((o) => {
        url = o.url
        setOverlay(o)
      }, () => {})
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => {
      controller.abort()
      if (url) URL.revokeObjectURL(url)
    }
  }, [active, selected, pol])

  return { scenes, selected, setSelected, pol, setPol, opacity, setOpacity, overlay, loading }
}

export type NisarScenesController = ReturnType<typeof useNisarScenes>
