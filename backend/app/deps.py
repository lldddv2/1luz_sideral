from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.nisar_extractor import NisarExtractor
from app.services.jobs import JobRegistry


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Set on app.state by the lifespan in app/main.py. Tests override get_extractor.
def get_extractor(request: Request) -> NisarExtractor:
    return request.app.state.extractor


def get_jobs(request: Request) -> JobRegistry:
    return request.app.state.jobs


def get_inventories_dir(request: Request) -> Path:
    return request.app.state.inventories_dir


ExtractorDep = Annotated[NisarExtractor, Depends(get_extractor)]
JobsDep = Annotated[JobRegistry, Depends(get_jobs)]
InventoriesDirDep = Annotated[Path, Depends(get_inventories_dir)]
