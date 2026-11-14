# Herramienta de extracción NISAR

Paquete Python y CLI para descubrir productos NISAR con ASF Search y pedir a
NASA Harmony subconjuntos espaciales de variables científicas como GeoTIFF.
El flujo evita descargar los HDF5 originales completos.

## Flujo

1. ASF Search encuentra granules que intersectan una BBOX, GeoJSON o WKT para
   fechas, producto y configuración indicados.
2. La CLI guarda inventario con IDs, fechas, geometría, tamaño de catálogo y
   variables anunciadas.
3. El usuario selecciona explícitamente IDs y variables.
4. Antes de extraer, el cliente consulta capacidades Harmony de la colección.
   Harmony genera GeoTIFF solo si el servicio anuncia el formato y las
   operaciones solicitadas.

Para autenticación, `asf_search`/Harmony usan Earthdata Login configurado en
`~/.netrc`. El código no pide ni imprime credenciales.

## Requisitos

- Fedora 43 u otra plataforma con Python 3.14 compatible.
- Cuenta Earthdata Login activa.
- Acceso HTTPS a ASF, CMR, Harmony y Earthdata Login.

## Instalar

Desde este directorio:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-nisar-extractor.txt
```

Configura `~/.netrc` fuera del repositorio. Abre el archivo con:

```bash
nano ~/.netrc
```

Pega esta estructura y sustituye los marcadores por tu cuenta:

```text
machine urs.earthdata.nasa.gov
  login TU_USUARIO_EARTHDATA
  password TU_CONTRASEÑA_EARTHDATA
```

Guarda el archivo y limita sus permisos:

```bash
chmod 600 ~/.netrc
.venv/bin/python -c 'import netrc; print("Earthdata configurado" if netrc.netrc().authenticators("urs.earthdata.nasa.gov") else "Falta Earthdata Login")'
```

No agregues `.netrc` al repositorio. Este directorio incluye reglas de
`.gitignore` para credenciales, entornos, cachés y descargas científicas.

## Buscar sin descargar

Desde este directorio, el siguiente ejemplo consulta GCOV PR para un WKT
pequeño y guarda el inventario. El comando `search` no descarga datos:

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
  --output-dir nisar_output \
  --inventory nisar_output/inventory.json
```

También se aceptan `--bbox OESTE,SUR,ESTE,NORTE` y archivos `--geojson`.
Revisa el inventario y copia el `product_id` y nombre variable exacto que
quieras solicitar.

## Seleccionar y extraer

El ejemplo selecciona un producto del inventario y una variable GCOV. Sustituye
el ID por uno que exista en tu inventario:

```bash
.venv/bin/python -m nisar_extractor.cli extract \
  --inventory nisar_output/inventory.json \
  --product-id NISAR_L2_PR_GCOV_..._001 \
  --variables /science/LSAR/GCOV/grids/frequencyA/HHHH \
  --output-dir nisar_output \
  --max-area-km2 2 \
  --max-products 1 \
  --max-output-mib 64 \
  --max-concurrent 1
```

El resultado GeoTIFF y los JSON de metadatos/capacidades quedan en
`nisar_output/`. El ledger SQLite registra trabajos y evita duplicar envíos.
Para ejecutar las pruebas locales sin solicitudes externas:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Documentación completa

Consulta [`NISAR_EXTRACTOR.md`](NISAR_EXTRACTOR.md) para límites, autenticación,
variables, máscara local de polígonos, manejo de trabajos y uso desde Python.

Fuentes oficiales: [ASF `asf_search`](https://docs.asf.alaska.edu/asf_search/basics/),
[colecciones NISAR](https://nisar-docs.asf.alaska.edu/earthdata-search/) y
[Harmony para NISAR](https://nisar-docs.asf.alaska.edu/harmony/).
