# Regions and natural features

## Administrative regions

Typing two or more characters searches administrative regions (countries, departments or states, provinces, municipalities, cities) after a short pause. Enter also triggers the search. Results appear under **Lugares** (Places) with a Spanish type such as País (Country), Departamento / Estado (Department / State), Provincia, Municipio or Ciudad.

- Click a result to fly to it and preview its outline.
- Click **+** to add its polygon as a study area.
- To remove a preview outline, right-click it and choose **Quitar contorno** (Remove outline), or clear the search with ✕.

When study areas exist, results are limited to them and the group reads "Lugares (en el área)". With no match the app shows "Ningún lugar en el área seleccionada" (No place in the selected area) and a button **Buscar en todo el mundo** (Search worldwide).

## Natural features

The app ships a world catalogue of 211 named natural features from Natural Earth plus manual additions: deserts, glaciers, volcanoes, wetlands, jungles, forests, mangroves and tundra.

- Typing a category word (Spanish or English, for example "volcanes" or "desert") shows the group "{category} (mundo)" with a row "Mostrar N … en el mapa" (Show N … on the map) that puts every feature of that category on the map as labels.
- Typing a name shows matching features. Click one to fly to it and show its outline. Click **+** to add it as a study area.
- On the map, an active feature label shows a **+ Área** button that adds it as a study area.
- A chip such as "Volcanes 27 ×" clears the labels.

With study areas, only features that intersect them are listed and the group reads "(en área)". With no match the app shows "Ningún lugar natural en el área seleccionada." and **Buscar en todo el mundo**.

```{note}
Some small manually added features have no outline. They use their bounding rectangle instead.
```

## Place names inside the area

When a study area exists, the basemap place labels are hidden and replaced with names inside the area only, fetched from OpenStreetMap (Overpass). Villages are included only when the areas total 20 000 km² or less; otherwise only states, cities and towns. Labels appear by zoom: states from 5, cities from 6, towns from 9, villages from 12. Spanish names are used when available. If the request fails, the area shows no names and the map still works.
