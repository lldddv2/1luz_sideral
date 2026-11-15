import json
import re
import uuid
from pathlib import Path
from typing import Any

from shapely.errors import ShapelyError

from app.nisar_extractor import Inventory, NisarExtractor, ProductRecord

# Inventory IDs are uuid4 hex; validating them keeps client input out of file paths.
_INVENTORY_ID = re.compile(r"[0-9a-f]{32}")
# NISAR_L2_PR_GCOV_<cycle>_<track>_<A|D>_<frame>_..., e.g. NISAR_L2_PR_GCOV_034_091_A_022_4005_...
_ID_ORBIT = re.compile(r"NISAR_L\d_[A-Z]{2}_[A-Z0-9]+_\d{3}_(\d{3})_([AD])_(\d{3})_")
_DIRECTION_BY_CODE = {"A": "ascending", "D": "descending"}
_DIRECTION_BY_WORD = {"ASCENDING": "ascending", "DESCENDING": "descending"}


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
    max_results: int = 100,
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
        max_results=max_results,
        inventory_path=_inventory_path(inventories_dir, inventory_id),
    )
    return inventory_id, inventory


def _whole_number(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def orbit_fields(product: ProductRecord) -> dict[str, Any]:
    """Track, direction and frame of a product. The product ID is read first, then ASF properties.

    Each value is None when neither source yields it.
    """
    match = _ID_ORBIT.match(product.product_id)
    if match:
        track, code, frame = match.groups()
        return {"track": int(track), "direction": _DIRECTION_BY_CODE[code], "frame": int(frame)}
    props = product.properties
    return {
        "track": _whole_number(props.get("pathNumber")),
        "direction": _DIRECTION_BY_WORD.get(str(props.get("flightDirection") or "").upper()),
        "frame": _whole_number(props.get("frameNumber")),
    }


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
