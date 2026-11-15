# Capas de agua en Colombia: verificación

Script: `bench/bench_water_colombia.py` (reusa `bench_water_layers.py`). Resultado: `bench_output/bench_water_colombia.json`.
Prueba real del 2026-11-15, 39 teselas en total (límite 150). NISAR y DSWx-S1 en z8 vía GIBS (EPSG:3857); JRC GSW en z10. Todas las respuestas fueron HTTP 200.
Un píxel cuenta como dato cuando su alfa es mayor que 0 (PIL). Se probaron fechas de NISAR cada 12 días hacia atrás desde 2026-11-13.

| región | bbox (O,S,E,N) | fecha NISAR con datos | fecha DSWx cercana | JRC | veredicto |
|---|---|---|---|---|---|
| La Mojana (Sucre/Bolívar) | -75.2, 8.2, -74.4, 9.0 | 2026-11-01 (2/2) | 2026-11-01 (2/2) | occurrence y change 2/2 | OK |
| Ciénaga Grande de Santa Marta | -74.6, 10.6, -74.2, 11.1 | 2026-11-01 (1/1) | 2026-11-01 (1/1) | 2/2 | OK |
| Depresión Momposina | -74.8, 8.9, -74.2, 9.4 | 2026-11-01 (2/2) | 2026-11-01 (2/2) | 2/2 | OK |
| Llanos (Arauca/Casanare) | -71.5, 5.5, -70.0, 6.8 | sin datos (7 fechas, de 09-02 a 11-13) | 2026-11-13 (1/1) | 2/2 | NISAR no disponible |

Notas:
- La fecha 2026-11-13 no tuvo píxeles de NISAR en ninguna región. Usar 2026-11-01.
- No se buscaron eventos de inundación de 2025–2026 en la web (sin verificar). La Mojana y Momposina se inundan cada temporada de lluvias (oct–nov).
- La comprobación muestra que hay píxeles, pero no si los colores son útiles. Revisar visualmente.

## Área y fecha recomendadas para la demo
La Mojana. bbox `[-75.2, 8.2, -74.4, 9.0]`, fecha `2026-11-01` para NISAR GCOV y DSWx-S1, más JRC occurrence/change de fondo. Centro `[-74.8, 8.6]`, zoom 9 (8 para ver también Momposina).
