# Interface overview

The app is a single map page with four main parts.

## Search bar

At the top of the map. It searches administrative regions, natural features and land-cover classes in one field. Press `Ctrl K` (or `Cmd K`) to focus it. See {doc}`search-and-landcover` and {doc}`regions-and-features`.

## Sidebar

A vertical rail of icons opens the sidebar sections:

- **Área de estudio** (Study area): draw or add the polygon(s) that limit searches.
- **Puntos de interés** (Points of interest): square zones used for downloads. See {doc}`points-of-interest`.
- **Coberturas** (Land covers): land-cover percentages of the active area.
- **Descarga** (Download): download data for the selected point of interest.
- **Modelo propio** (Own model): connect an external model. See {doc}`custom-model`.
- **Capas** (Layers): toggle overlays such as `OPERA DSWx-S1`, `NISAR GCOV (vista previa)` and `JRC agua histórica`.
- **Acerca** (About).
- **Ver guía** (Show guide): restart the guided tour. See {doc}`onboarding-tour`.

The panel can be collapsed with **Plegar panel** (Collapse panel) and reopened with **Expandir panel** (Expand panel).

## Acquisition timeline

The bar at the bottom lists NISAR pass dates for the study area and plays them as an animation. See {doc}`timeline-playback`.

## Map

The MapLibre map shows the basemap, study areas, points of interest, land-cover masks, model results and labels.

## Conventions

- Every button has an icon in front of its text. Icon-only buttons show a tooltip.
- Status words are fixed: **Buscando** (Searching), **En cola** (Queued), **Procesando** (Processing), **Listo** (Done), **Error**.
- Warnings use yellow with a triangle icon. A warning never disables a button.
- Multi-select segmented buttons show a check mark when selected and a plus sign when not.
