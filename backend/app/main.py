import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.deps import get_settings
from app.nisar_extractor import ExtractionConfig, NisarExtractor
from app.routers import estimate, health, jobs, search
from app.services.jobs import JobRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.netrc:
        os.environ["NETRC"] = settings.netrc
    data_dir = Path(settings.data_dir)
    # The extractor keeps its job ledger (SQLite) in output_dir, so it lands under data_dir.
    # Harmony auth: EARTHDATA_USERNAME/PASSWORD first, else NETRC or ~/.netrc.
    extractor = NisarExtractor(
        ExtractionConfig(output_dir=str(data_dir / "nisar")),
        earthdata_auth=settings.earthdata_auth,
    )
    app.state.extractor = extractor
    app.state.inventories_dir = data_dir / "inventories"
    app.state.jobs = JobRegistry()
    try:
        yield
    finally:
        extractor.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="1luz_sideral API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (health.router, search.router, jobs.router):
        app.include_router(router, prefix="/api")
    app.include_router(estimate.router, prefix="/api")
    return app


app = create_app()
