# NISAR ASF/Harmony extractor

Este paquete implementa exclusivamente descubrimiento de productos y extracción
de variables mediante ASF Search y NASA Harmony. No contiene análisis temporal,
detección de cambios ni interpretación científica. Está separado de
las pruebas exploratorias previas; funciona como paquete autónomo.

## Requisitos y autenticación

Probado en Fedora 43 con Python 3.14. Instala dependencias en el entorno del
proyecto:

```bash
.venv/bin/python -m pip install -r requirements-nisar-extractor.txt
```

Harmony usa Earthdata Login mediante el `~/.netrc` existente. La biblioteca
`requests` y `harmony-py` leen esa configuración; el módulo nunca solicita,
escribe o imprime la contraseña. En Linux, restringe sus permisos:

```bash
chmod 600 ~/.netrc
.venv/bin/python -c 'import netrc; print("EDL configurado" if netrc.netrc().authenticators("urs.earthdata.nasa.gov") else "Falta EDL")'
```

No se crean tokens nuevos. La opción IPv4 se activa por defecto por el problema
de ruta IPv6 que ya se comprobó en este Fedora; desactívala con
`--no-force-ipv4` si tu red tiene IPv6 funcional.

## Flujo de trabajo

`search` consulta catálogo y capacidades, guarda un inventario y **no descarga
datos**. `extract` exige IDs de productos y variables explícitos; no descarga la
URL ASF del HDF5. Envía una petición Harmony para cada selección, recupera
únicamente resultados GeoTIFF y registra jobs en SQLite para reanudarlos o
reutilizarlos.

### Buscar por BBOX, GeoJSON o WKT

Debe proporcionarse exactamente una geometría. BBOX usa orden
`oeste,sur,este,norte`; GeoJSON debe ser Polygon/MultiPolygon (también se acepta
Feature/FeatureCollection); WKT debe ser Polygon/MultiPolygon en longitud/latitud.
ASF recibe WKT `intersectsWith`, más las fechas, producto y configuración.

Ejemplo pequeño con la región de la PoC, fechas originales, GCOV PR y un máximo
de un producto:

```bash
.venv/bin/python -m nisar_extractor.cli search \
  --wkt 'POLYGON((-105.0048 39.9952,-104.9952 39.9952,-105.0000 40.0048,-105.0048 39.9952))' \
  --start 2025-08-01T05:00:00Z \
  --stop 2026-11-15T04:59:59Z \
  --product GCOV \
  --production-configuration PR \
  --max-results 1 \
  --max-products 1 \
  --max-area-km2 2 \
  --output-dir nisar_extractor_output \
  --inventory nisar_extractor_output/inventory.json
```

`--product` acepta GCOV, GUNW, GOFF o SME2. `max-area-km2` es geodésico WGS84.
El BBOX continental original de Vertex supera el máximo prudente por defecto;
puedes elevar el límite explícitamente para la **búsqueda**, pero conserva un AOI
pequeño para la extracción. Incluso si la configuración aumenta el límite de
bytes, el programa nunca abre el URL ASF del `.h5`.

El inventario JSON contiene ID de producto y de CMR granule, short name y concept
ID de colección, fechas, huella GeoJSON, `granule_size` de CMR en MB, una
conversión estimada a bytes y variables listadas para la colección. El tamaño en
bytes es estimado desde el valor MB de CMR; se conservan ambos campos. Las
variables proceden de capacidades de colección y no garantizan que cada una
exista en todos los granules; Harmony valida la extracción real.

### Seleccionar explícitamente y extraer

Primero revisa el inventario y copia `product_id` y una variable completa. El
extractor vuelve a consultar capacidades actuales antes de solicitar Harmony:

```bash
.venv/bin/python -m nisar_extractor.cli extract \
  --inventory nisar_extractor_output/inventory.json \
  --product-id NISAR_L2_PR_GCOV_..._001 \
  --variables /science/LSAR/GCOV/grids/frequencyA/HHHH \
  --output-dir nisar_extractor_output \
  --max-area-km2 2 \
  --max-products 1 \
  --max-output-mib 64 \
  --max-concurrent 1
```

Se pueden repetir `--product-id` para varios productos. La lista de
`--variables` es separada por comas y acepta nombres completos o IDs UMM-Var.
`--output-crs EPSG:4326` solo se acepta si el servicio GeoTIFF lo anuncia. El
default conserva el CRS de origen.

Para reanudar un job conocido sin enviar otro POST:

```bash
.venv/bin/python -m nisar_extractor.cli extract \
  --inventory nisar_extractor_output/inventory.json \
  --product-id NISAR_L2_PR_GCOV_..._001 \
  --variables /science/LSAR/GCOV/grids/frequencyA/HHHH \
  --reuse-job-id UUID-DE-HARMONY \
  --output-dir nisar_extractor_output
```

Los resultados locales se verifican y reutilizan en la siguiente invocación si
request key y archivo coinciden. Para ver el registro de trabajos:

```bash
.venv/bin/python -m nisar_extractor.cli jobs --output-dir nisar_extractor_output
```

El registro local `.nisar-extractor-jobs.sqlite3` almacena la clave idempotente,
job ID, estado, intentos, rutas, hashes y errores seguros. Los GET permiten
reintentos limitados. Un POST con respuesta de red ambigua queda como
`submission_unknown`; no se vuelve a enviar automáticamente porque Harmony pudo
haber creado el job. Los jobs fallidos confirmados sí admiten reintento hasta
`--max-attempts`. Esta distinción evita duplicados.

Cada resultado pasa por estos controles antes de quedar publicado: URL `.tif` o
`.tiff`, MIME TIFF aceptado, tope de bytes durante el streaming, validación de
`Content-Length` cuando viene, firma TIFF/BigTIFF, apertura con Rasterio y SHA256
local. Un resultado inválido se borra. Los HDF5 no son formatos aceptados por el
descargador.

Harmony puede admitir bbox y variable pero no shape para una colección. En ese
caso el request usa el bbox y Rasterio crea un segundo TIFF enmascarado según el
GeoJSON/WKT original. Si el servicio GeoTIFF anuncia shape, se envía el polígono
como GeoJSON. La decisión se basa en capacidades del servicio `nasa/harmony-gdal-adapter`,
no en el resumen de una colección ni en una vista previa PNG.

Cada extracción guarda un JSON de metadatos y un snapshot de capacidades junto
al TIFF. Se registran el granule, fechas, huella, variable, CRS, salida,
capabilities version, job, tamaño de transferencia, checksum y si se aplicó
máscara local.

## Uso desde Python/FastAPI

La clase no depende de FastAPI; un endpoint puede hacer búsqueda síncrona breve y
delegar extracción bloqueante a un worker/cola. No mantengas un request HTTP del
navegador abierto mientras Harmony procesa el job:

```python
from nisar_extractor import ExtractionConfig, NisarExtractor

extractor = NisarExtractor(ExtractionConfig(
    output_dir="data/nisar",
    max_area_km2=20,
    max_products=5,
    max_output_bytes=32 * 1024 * 1024,
    max_concurrent=2,
))

region = extractor.geojson("aoi.geojson")
inventory = extractor.discover(
    region,
    start="2025-08-01T05:00:00Z",
    stop="2026-11-15T04:59:59Z",
    product_type="GCOV",
    production_configuration="PR",
    max_results=5,
    inventory_path="data/nisar/inventory.json",
)

# La interfaz primero presenta inventory.products; el usuario elige IDs.
outputs = extractor.extract(
    inventory,
    product_ids=[inventory.products[0].product_id],
    variables=["/science/LSAR/GCOV/grids/frequencyA/HHHH"],
)
```

Para FastAPI usa un worker o `asyncio.to_thread` para no bloquear el event loop.
En despliegue con varias réplicas comparte almacenamiento/ledger con locking
adecuado o centraliza el ledger y la cola; SQLite local sirve para la PoC, no
como coordinador distribuido.

## Pruebas

Las pruebas unitarias no acceden a la red y crean un TIFF diminuto en memoria:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Documentación oficial consultada

- [ASF Search API: parámetros geográficos, temporales y resultados](https://docs.asf.alaska.edu/api/keywords/)
- [ASF `asf_search`: búsqueda y autenticación](https://docs.asf.alaska.edu/asf_search/basics/)
- [Colecciones validadas NISAR: nombres cortos](https://nisar-docs.asf.alaska.edu/earthdata-search/)
- [Guía NISAR de extracción y personalización Harmony](https://nisar-docs.asf.alaska.edu/harmony/)
- [Portal y API de NASA Harmony](https://harmony.earthdata.nasa.gov/)

La guía NISAR enumera `NISAR_L2_GCOV_V1` como colección GCOV validada y documenta la extracción de variables 2D HDF5 a COG/GeoTIFF, con recorte y reproyección. El programa consulta además el endpoint de capacidades en tiempo de ejecución: una capacidad anunciada para la colección o para una vista previa no se toma como prueba de que el adaptador GeoTIFF concreto la soporte.

### Prueba pequeña verificada en Fedora

La verificación de extremo a extremo realizada durante el desarrollo consultó
ASF en vivo, encontró un granule GCOV PR y extrajo la variable
`/science/LSAR/GCOV/grids/frequencyA/HHHH` mediante un job Harmony ya completado.
La descarga fue un único GeoTIFF de 39.032 bytes; Rasterio abrió el raster
84×110, y la aplicación de una máscara local produjo un segundo TIFF de 17.412
bytes. El SHA256 del resultado de Harmony fue
`29c7716b5a8542862dfb7a23c98186f29bfd43017881a5d2c8dd2a091999c7cf`.
El job `60ec0904-418f-4725-b38e-e7c79b3e4805` se reutilizó, no se creó otro job y
no se descargó ningún `.h5`. Esa corrida registró
`source_hdf5_downloaded: false`.

Los inventarios, TIFF y estado local de aquel entorno no se incluyen aquí. Para
repetir la prueba, sigue los ejemplos de búsqueda y extracción de esta guía y
usa un ID que aparezca en el inventario nuevo.
