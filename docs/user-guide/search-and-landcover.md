# Search and land cover

The search bar searches places and land covers at the same time. Its placeholder reads "Buscar lugar o cobertura (p. ej. humedales)…" (Search place or cover, e.g. wetlands).

## Result groups

The dropdown shows several groups:

- Natural features and places (see {doc}`regions-and-features`).
- **Coberturas en {area}** (Covers in {area}): land-cover classes of the active study area, each with a color dot, class name and percentage.

The land-cover group appears only when a study area exists. The active area is the last one in the list, the same one used by the download section and the timeline.

## Spanish synonyms

Land-cover matching is case- and accent-insensitive, matches prefixes and also matches the start of any word (`desnudo` matches "suelo desnudo"). Queries shorter than two characters do not match.

| Class | Accepted words |
|---|---|
| wetland | humedal(es), pantano, ciénaga, turbera, marisma |
| tree | bosque(s), selva, árboles, forestal |
| snow_ice | glaciar(es), hielo, nieve |
| water | agua, lago, laguna, río, embalse |
| cropland | cultivo(s), agrícola, agricultura |
| built_up | urbano, ciudad, construido |
| mangrove | manglar(es) |
| grassland | pastizal, pradera, pasto |
| shrubland | matorral, arbustos |
| bare | desierto, suelo desnudo, árido |
| moss | musgo, liquen, tundra |

## Filter chips

Clicking a land-cover row adds a chip under the search bar, for example "● Humedal 12,4 % ×". Clicking the row again removes it. Several chips can be active. The chips are the filter.

When the chips change, the app requests a mask of the selected classes (ESA WorldCover) for the active area and draws it on the map at 70 % opacity, below the area outline. Changing or deleting the area clears the mask and reloads the statistics.

## Coberturas section

The **Coberturas** sidebar section shows a horizontal bar per class with its percentage. Clicking a bar adds or removes the same chip as the search bar.

## Errors

- "Área no válida o demasiado grande." (Invalid or too large area): the area is invalid or exceeds 2 000 000 km².
- "No se pudo leer la cobertura WorldCover." (Could not read WorldCover): the land-cover source failed.

```{note}
Editing an area's geometry does not refresh its statistics or mask. Delete and re-add the area instead.
```
