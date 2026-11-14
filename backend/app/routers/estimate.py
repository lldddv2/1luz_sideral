from fastapi import APIRouter, HTTPException

from app.deps import InventoriesDirDep
from app.schemas import EstimateRequest, EstimateResponse
from app.services import estimate as estimate_service
from app.services import nisar

router = APIRouter(tags=["estimate"])


# Sync like /search: an inventory file may be read. Makes no network calls.
@router.post("/estimate", response_model=EstimateResponse)
def estimate(body: EstimateRequest, inventories_dir: InventoriesDirDep) -> EstimateResponse:
    inventory = None
    if body.inventory_id is not None:
        try:
            inventory = nisar.load_inventory(inventories_dir, body.inventory_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, KeyError, TypeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        result = estimate_service.estimate(
            body.geometry,
            variables=body.variables,
            products=body.products,
            spacing_m=body.spacing_m,
            bytes_per_pixel=body.bytes_per_pixel,
            inventory=inventory,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return EstimateResponse(**result)
