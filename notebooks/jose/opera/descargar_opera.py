#!/usr/bin/env python3
"""Descarga una capa categórica de OPERA DIST-ALERT o DSWx-HLS."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

import earthaccess


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "datos_opera"

# Área de ejemplo en Colorado. Se pueden cambiar con las opciones de CLI.
DEFAULT_BBOX = (-105.05, 39.95, -104.95, 40.05)
DEFAULT_START = "2026-10-01"
DEFAULT_END = "2026-11-14"

PRODUCTS = {
    "DIST-ALERT": {
        "short_name": "OPERA_L3_DIST-ALERT-HLS_V1",
        "layer_suffix": "_VEG-DIST-STATUS.tif",
        "provider": "LPCLOUD",
    },
    "DSWx-HLS": {
        "short_name": "OPERA_L3_DSWX-HLS_V1",
        "layer_suffix": "_B01_WTR.tif",
        "provider": "POCLOUD",
    },
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Busca y descarga una capa GeoTIFF categórica de NASA OPERA."
    )
    parser.add_argument(
        "--product", choices=["DIST-ALERT", "DSWx-HLS", "all"], default="all",
        help="producto OPERA que se buscará (predeterminado: all)",
    )
    parser.add_argument(
        "--bbox", nargs=4, type=float, metavar=("OESTE", "SUR", "ESTE", "NORTE"),
        default=DEFAULT_BBOX, help="límites WGS84 en grados (orden oeste sur este norte)",
    )
    parser.add_argument("--start", default=DEFAULT_START, help="fecha inicial YYYY-MM-DD")
    parser.add_argument("--end", default=DEFAULT_END, help="fecha final YYYY-MM-DD")
    parser.add_argument(
        "--count", type=int, default=3,
        help="máximo de granules consultados por producto (predeterminado: 3)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="descargar sin solicitar confirmación interactiva"
    )
    return parser.parse_args(argv)


def matching_layer_urls(granule: object, suffix: str) -> list[str]:
    """Return only URLs whose path ends in the requested layer name."""
    return [
        url for url in granule.data_links(access="external")
        if urlparse(url).path.upper().endswith(suffix.upper())
    ]


def confirm_download(product: str, filename: str, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    answer = input(f"¿Descargar {product} / {filename}? [s/N]: ")
    return answer.strip().lower() in {"s", "si", "sí", "y", "yes"}


def run(args: argparse.Namespace) -> int:
    if args.count < 1:
        raise ValueError("--count debe ser al menos 1")
    west, south, east, north = args.bbox
    if west >= east or south >= north:
        raise ValueError("BBOX inválido: se requiere oeste < este y sur < norte")
    if args.start > args.end:
        raise ValueError("--start debe ser anterior o igual a --end")

    # No imprime las credenciales. earthaccess las toma de ~/.netrc,
    # variables de entorno compatibles o interacción segura en terminal.
    earthaccess.login(strategy="netrc")
    names = list(PRODUCTS) if args.product == "all" else [args.product]
    errors = 0

    for name in names:
        config = PRODUCTS[name]
        print(f"\n=== {name} ===")
        granules = earthaccess.search_data(
            short_name=config["short_name"],
            bounding_box=tuple(args.bbox),
            temporal=(args.start, args.end),
            count=args.count,
        )
        print(f"Granules encontrados: {len(granules)}")

        match: tuple[object, str] | None = None
        for granule in granules:
            urls = matching_layer_urls(granule, config["layer_suffix"])
            if urls:
                match = (granule, urls[0])
                break
        if match is None:
            print(f"No se encontró la capa {config['layer_suffix']} en los resultados.")
            continue

        _, url = match
        filename = Path(urlparse(url).path).name
        print(f"Capa seleccionada: {filename}")
        if not confirm_download(name, filename, args.yes):
            print("Omitida por el usuario.")
            continue

        destination = DATA_DIR / name
        destination.mkdir(parents=True, exist_ok=True)
        try:
            files = earthaccess.download(
                [url],
                local_path=str(destination),
                provider=config["provider"],
                threads=1,
            )
            print("Archivos descargados:", *(str(path) for path in files), sep="\n  ")
        except Exception as error:
            errors += 1
            print(f"Error al descargar {name}: {type(error).__name__}: {error}")

    print(f"\nDirectorio de salida: {DATA_DIR}")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except Exception as error:
        print(f"Error: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
