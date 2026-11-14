from fastapi import APIRouter, HTTPException

from app.deps import ExtractorDep, InventoriesDirDep
from app.schemas import AOIRequest, Product, SearchResponse
from app.services import nisar

router = APIRouter(tags=["search"])


# Sync on purpose: ASF and CMR calls block, so FastAPI runs this in a threadpool.
@router.post("/search", response_model=SearchResponse)
def search(body: AOIRequest, extractor: ExtractorDep, inventories_dir: InventoriesDirDep) -> SearchResponse:
    try:
        inventory_id, inventory = nisar.search(
            extractor, inventories_dir, body.geometry, body.start, body.end
        )
    except nisar.InvalidGeometryError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return SearchResponse(
        inventory_id=inventory_id,
        products=[Product.model_validate(product.to_dict()) for product in inventory.products],
    )
