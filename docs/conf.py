"""Sphinx configuration for the 1luz_sideral documentation."""
import os
import sys

DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(DOCS_DIR, "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(DOCS_DIR, "..", "model_service")))

project = "1luz_sideral"
author = "1luz_sideral team"
copyright = "2026, 1luz_sideral team"
release = "0.1.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_copybutton",
]

myst_enable_extensions = ["colon_fence", "deflist"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

# Heavy or native dependencies are mocked so autodoc works without installing them.
autodoc_mock_imports = [
    "fastapi", "starlette", "uvicorn",
    "asf_search", "harmony", "requests", "httpx", "numpy", "shapely",
    "pyproj", "rasterio", "torch", "h5py", "xarray", "multipart",
]
autodoc_default_options = {"members": True, "undoc-members": False}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_title = "1luz_sideral documentation"
