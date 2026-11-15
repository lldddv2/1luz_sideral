# Search and land cover

The search bar searches places and land covers at the same time. Its placeholder reads "Search places, wetlands, glaciers, deserts…".

## Result groups

The dropdown shows several groups:

- Natural features and places (see {doc}`regions-and-features`).
- **Land cover in {area}**: land-cover classes of the active study area, each with a color dot, class name and percentage.

The land-cover group appears only when a study area exists. The active area is the last one in the list, the same one used by the download section and the timeline.

## Synonyms

Land-cover matching is case- and accent-insensitive, matches prefixes and also matches the start of any word (`soil` matches "bare soil"). English and Spanish words both work. Queries shorter than two characters do not match.

| Class | Accepted words |
|---|---|
| wetland | wetland(s), swamp, marsh, bog, peatland; humedal(es), pantano, ciénaga, turbera, marisma |
| tree | forest(s), tree(s), jungle, woodland; bosque(s), selva, árboles, forestal |
| snow_ice | glacier(s), ice, snow; glaciar(es), hielo, nieve |
| water | water, lake, lagoon, river, reservoir; agua, lago, laguna, río, embalse |
| cropland | cropland, crop(s), farmland, agriculture; cultivo(s), agrícola, agricultura |
| built_up | urban, city, built-up, built up; urbano, ciudad, construido |
| mangrove | mangrove(s); manglar(es) |
| grassland | grassland, grass, meadow, prairie; pastizal, pradera, pasto |
| shrubland | shrubland, shrub(s), scrub; matorral, arbustos |
| bare | desert, bare, bare soil, arid; desierto, suelo desnudo, árido |
| moss | moss, lichen, tundra; musgo, liquen |

## Filter chips

Clicking a land-cover row adds a chip under the search bar, for example "● Herbaceous wetland 12.4 % ×". Clicking the row again removes it. Several chips can be active. The chips are the filter.

When the chips change, the app requests a mask of the selected classes (ESA WorldCover) for the active area and draws it on the map at 70 % opacity, below the area outline. Changing or deleting the area clears the mask and reloads the statistics.

## Land cover section

The **Land cover** sidebar section shows a horizontal bar per class with its percentage. Clicking a bar adds or removes the same chip as the search bar.

## Errors

- "Invalid or too large area.": the area is invalid or exceeds 2 000 000 km².
- "Could not read WorldCover land cover.": the land-cover source failed.

```{note}
Editing an area's geometry does not refresh its statistics or mask. Delete and re-add the area instead.
```
