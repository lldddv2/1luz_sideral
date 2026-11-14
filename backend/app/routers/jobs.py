from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.deps import ExtractorDep, InventoriesDirDep, JobsDep
from app.nisar_extractor import Inventory, NisarExtractor
from app.nisar_extractor.harmony_service import safe_error
from app.schemas import Job, JobCreate
from app.services import nisar
from app.services.jobs import JobRegistry

router = APIRouter(tags=["jobs"])


def _run_job(
    extractor: NisarExtractor,
    jobs: JobRegistry,
    job_id: str,
    inventory: Inventory,
    body: JobCreate,
) -> None:
    jobs.update(job_id, state="running")
    try:
        results = nisar.extract(
            extractor, inventory, body.product_ids, body.variables, body.output_crs
        )
    except Exception as error:  # record the failure on the job; per-product errors live in results
        jobs.update(job_id, state="failed", error=f"{type(error).__name__}: {safe_error(error)}")
        return
    jobs.update(job_id, state="done", results=results)


@router.post("/jobs", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    body: JobCreate,
    background: BackgroundTasks,
    extractor: ExtractorDep,
    jobs: JobsDep,
    inventories_dir: InventoriesDirDep,
) -> Job:
    try:
        inventory = nisar.load_inventory(inventories_dir, body.inventory_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    known = {product.product_id for product in inventory.products}
    unknown = [product_id for product_id in body.product_ids if product_id not in known]
    if unknown:
        raise HTTPException(status_code=400, detail=f"product_ids not in inventory: {unknown}")

    job = jobs.create(body)
    background.add_task(_run_job, extractor, jobs, job.id, inventory, body)
    return job


@router.get("/jobs", response_model=list[Job])
def list_jobs(jobs: JobsDep) -> list[Job]:
    return jobs.list_all()


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, jobs: JobsDep) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job
