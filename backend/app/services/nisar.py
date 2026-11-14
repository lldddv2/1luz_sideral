import json
import re
import uuid
from pathlib import Path
from typing import Any

from shapely.errors import ShapelyError

from app.nisar_extractor import Inventory, NisarExtractor

# Inventory IDs are uuid4 hex; validating them keeps client input out of file paths.
_INVENTORY_ID = re.compile(r"[0-9a-f]{32}")


class InvalidGeometryError(ValueError):
    """Client AOI GeoJSON that Shapely cannot parse, such as an unknown type."""


def _inventory_path(inventories_dir: Path, inventory_id: str) -> Path:
    if not _INVENTORY_ID.fullmatch(inventory_id):
        raise ValueError("inventory_id must be a 32-character lowercase hex string")
    return inventories_dir / f"{inventory_id}.json"


def search(
    extractor: NisarExtractor,
    inventories_dir: Path,
    geometry: dict[str, Any],
    start: str,
    end: str,
) -> tuple[str, Inventory]:
    """Discover GCOV PR products over the AOI and save the inventory JSON. Downloads nothing."""
    try:
        region = NisarExtractor.geojson(geometry)
    except ShapelyError as error:
        raise InvalidGeometryError(f"Invalid GeoJSON geometry ({type(error).__name__}): {error}") from error
    inventory_id = uuid.uuid4().hex
    inventory = extractor.discover(
        region,
        start=start,
        stop=end,
        product_type="GCOV",
        production_configuration="PR",
        max_results=10,
        inventory_path=_inventory_path(inventories_dir, inventory_id),
    )
    return inventory_id, inventory


def load_inventory(inventories_dir: Path, inventory_id: str) -> Inventory:
    path = _inventory_path(inventories_dir, inventory_id)
    if not path.is_file():
        raise FileNotFoundError(f"Unknown inventory_id: {inventory_id}")
    return Inventory.from_dict(json.loads(path.read_text()))


def extract(
    extractor: NisarExtractor,
    inventory: Inventory,
    product_ids: list[str],
    variables: list[str],
    output_crs: str | None,
) -> list[dict[str, Any]]:
    return extractor.extract(
        inventory,
        product_ids=product_ids,
        variables=variables,
        output_crs=output_crs,
    )
