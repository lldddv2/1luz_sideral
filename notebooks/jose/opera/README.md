# Herramientas de exploración NASA OPERA

Esta carpeta contiene dos programas independientes de la herramienta NISAR:

- `descargar_opera.py` busca y descarga una capa GeoTIFF de OPERA usando NASA Earthdata.
- `inspeccionar_opera.py` inspecciona los GeoTIFF locales y produce mapas categóricos, estadísticas y metadatos JSON.

## Productos y variables

- **OPERA DIST-ALERT-HLS** informa el estado de perturbación de vegetación. El programa descarga la banda `VEG-DIST-STATUS`.
- **OPERA DSWx-HLS** clasifica agua superficial. El programa descarga la banda `B01_WTR`.

Los códigos de clase y sus etiquetas se basan en las especificaciones de producto oficiales indicadas en el reporte del inspector. Los colores de DIST-ALERT son una paleta de visualización, no una codificación científica adicional.

## Requisitos e instalación

Se necesita Python 3.12 o posterior, conexión a internet para buscar/descargar, una cuenta gratuita de NASA Earthdata Login y espacio local para los GeoTIFF seleccionados. Las versiones fijadas en `requirements.txt` requieren Python 3.12+ (Fedora 43 con Python 3.14 es compatible).

Desde esta carpeta, crear e instalar en un entorno virtual:

```bash
cd opera
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

En Fedora puede ser necesario instalar primero herramientas de compilación y librerías geoespaciales del sistema si `pip` no encuentra una rueda compatible. Las ruedas de Rasterio incluyen GDAL para los entornos Python soportados habituales.

## Configurar NASA Earthdata Login

Registra la cuenta en [NASA Earthdata Login](https://urs.earthdata.nasa.gov/). Aunque `earthaccess` también permite variables de entorno y autenticación interactiva, este programa usa explícitamente `~/.netrc`; no pongas credenciales en el código ni en Git.

En Fedora/Linux, crea el archivo con el editor local:

```bash
nano ~/.netrc
```

Contenido (reemplaza los marcadores en tu editor; no compartas el archivo):

```text
machine urs.earthdata.nasa.gov
  login TU_USUARIO_EARTHDATA
  password TU_CONTRASEÑA_EARTHDATA
```

Restringe sus permisos:

```bash
chmod 600 ~/.netrc
```

La autenticación y la autorización para cada colección dependen de las políticas de NASA Earthdata. Nunca subas `.netrc` al repositorio.

## Buscar y descargar

Los valores predeterminados están en Colorado, del 1 de octubre al 14 de noviembre de 2026. También se pueden pasar los parámetros en la línea de comandos. El BBOX usa WGS84 y el orden `OESTE SUR ESTE NORTE`.

Consulta las opciones sin autenticación ni solicitudes de datos:

```bash
python descargar_opera.py --help
```

Buscar ambos productos y confirmar cada descarga en pantalla:

```bash
python descargar_opera.py --product all \
  --bbox -105.05 39.95 -104.95 40.05 \
  --start 2026-10-01 --end 2026-11-14 --count 3
```

Elegir un único producto:

```bash
python descargar_opera.py --product DSWx-HLS \
  --bbox -105.05 39.95 -104.95 40.05 \
  --start 2026-10-01 --end 2026-11-14 --count 1
```

`--yes` omite la confirmación por producto. Úsalo únicamente cuando el área, fechas y producto estén revisados. El programa busca como máximo `--count` granules por producto y descarga solo el primer enlace que coincide con la capa configurada. La salida se guarda bajo `opera/datos_opera/` y no depende del directorio desde el que se ejecuta el script.

## Inspeccionar y visualizar

Una vez descargados los GeoTIFF, desde esta carpeta ejecuta:

```bash
python inspeccionar_opera.py
```

El inspector busca recursivamente `.tif` y `.tiff` dentro de `datos_opera/`, procesa raster por bloques y crea resultados en:

```text
datos_opera/resultados/
├── *_mapa.png
└── reporte_inspeccion_opera.json
```

El PNG muestra las clases con una leyenda; los valores NoData aparecen transparentes. DSWx-HLS distingue agua abierta, agua superficial parcial y códigos de máscara (por ejemplo, nubes/sombras, nieve/hielo y océano). DIST-ALERT muestra clases de estado de perturbación; consulta el código y su descripción en el JSON y la especificación enlazada. Porcentajes por clase válida excluyen NoData y códigos enmascarados.

## Referencias oficiales

- [OPERA DIST-ALERT-HLS Product Specification](https://lpdaac.usgs.gov/documents/1766/OPERA_DIST_HLS_Product_Specification_V1.pdf)
- [OPERA DSWx-HLS Product Specification](https://d2pn8kiwq2w21t.cloudfront.net/documents/OPERA_DSWx-HLS_ProductSpec_v1.0.0_D-107395_RevB.pdf)
- [DSWx visualization guide](https://d2pn8kiwq2w21t.cloudfront.net/documents/DSWx_visualization_guide.pdf)
- [earthaccess: autenticación](https://earthaccess.readthedocs.io/en/stable/user/howto/authenticate/)
- [earthaccess: búsqueda y acceso a datos](https://earthaccess.readthedocs.io/en/stable/user/howto/access-data/)

Las búsquedas y descargas están sujetas a disponibilidad de datos, autorización Earthdata, políticas vigentes del archivo y espacio local. La búsqueda no garantiza que haya un granule para cada combinación de área y fecha.
