from pathlib import Path
from fastapi import APIRouter

from ...config.settings import Settings
from ...registry.extension_registry import ExtensionRegistry

router = APIRouter(tags=["Extensions"])


@router.get("/extensions")
async def list_extensions():
    settings = Settings.load()
    registry = ExtensionRegistry()
    ext_config_path = Path(settings.pipeline.extensions_config)
    if ext_config_path.exists():
        registry.load_from_config(ext_config_path)

    return {
        "extensions": [meta.model_dump() for meta in registry.list_extensions()]
    }
