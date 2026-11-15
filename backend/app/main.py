import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.deps import get_settings
from app.nisar_extractor import ExtractionConfig, NisarExtractor
from app.routers import dem, estimate, features, health, jobs, landcover, models, regions, samples, scenes, search, water
from app.services.jobs import JobRegistry


def ensure_netrc(netrc_setting: str | None = None) -> str | None:
    """Write a temp netrc from EARTHDATA_USERNAME/PASSWORD when no netrc exists.

    requests (water/service.py, nisar_extractor) only reads NETRC or ~/.netrc, so
    containers that pass credentials as env vars need this. Never logs secrets.
    """
    if netrc_setting or os.environ.get("NETRC"):
        return None
    home = Path(os.path.expanduser("~"))
    if (home / ".netrc").exists() or (home / "_netrc").exists():
        return None
    user = os.environ.get("EARTHDATA_USERNAME")
    password = os.environ.get("EARTHDATA_PASSWORD")
    if not user or not password:
        return None
    path = Path(tempfile.gettempdir()) / "luzsi.netrc"
    path.write_text(f"machine urs.earthdata.nasa.gov login {user} password {password}\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    os.environ["NETRC"] = str(path)
    return str(path)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.netrc:
        os.environ["NETRC"] = settings.netrc
    else:
        ensure_netrc()
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
    app.state.samples_dir = data_dir / "samples"
    app.state.water_dir = data_dir / "water"
    app.state.models_dir = data_dir / "models"
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
    app.include_router(landcover.router, prefix="/api")
    app.include_router(dem.router, prefix="/api")
    app.include_router(samples.router, prefix="/api")
    app.include_router(scenes.router, prefix="/api")
    app.include_router(features.router, prefix="/api")
    app.include_router(regions.router, prefix="/api")
    app.include_router(water.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    # Production: serve the built frontend (frontend/dist) from the same origin.
    static_dir = os.environ.get("STATIC_DIR")
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


app = create_app()
