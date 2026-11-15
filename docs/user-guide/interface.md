# Interface overview

The app is a single map page with four main parts.

## Search bar

At the top of the map. It searches administrative regions, natural features and land-cover classes in one field. Press `Ctrl K` (or `Cmd K`) to focus it. See {doc}`search-and-landcover` and {doc}`regions-and-features`.

## Sidebar

A vertical rail of icons opens the sidebar sections:

- **Study area**: draw or add the polygon(s) that limit searches.
- **Points of interest**: square zones used for downloads. See {doc}`points-of-interest`.
- **Land cover**: land-cover percentages of the active area.
- **Download**: download data for the selected point of interest.
- **Your model**: connect an external model. See {doc}`custom-model`.
- **Layers**: toggle overlays such as `OPERA DSWx-S1`, `NISAR GCOV (preview)` and `JRC historical water`.
- **About**.
- **Start tour**: restart the guided tour. See {doc}`onboarding-tour`.

The panel can be collapsed with **Collapse panel** and reopened with **Expand panel**.

## Acquisition timeline

The bar at the bottom lists NISAR pass dates for the study area and plays them as an animation. See {doc}`timeline-playback`.

## Map

The MapLibre map shows the basemap, study areas, points of interest, land-cover masks, model results and labels.

## Conventions

- Every button has an icon in front of its text. Icon-only buttons show a tooltip.
- Status words are fixed: **Searching**, **Queued**, **Processing**, **Done**, **Error**.
- Warnings use yellow with a triangle icon. A warning never disables a button.
- Multi-select segmented buttons show a check mark when selected and a plus sign when not.
