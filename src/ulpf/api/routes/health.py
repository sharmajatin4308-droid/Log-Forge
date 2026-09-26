import time
from fastapi import APIRouter

router = APIRouter(tags=["Health"])

_START_TIME_MONOTONIC = time.monotonic()


@router.get("/health")
async def health_check():
    uptime = time.monotonic() - _START_TIME_MONOTONIC
    return {
        "status": "ok",
        "version": "1.0.0",
        "ocsf_version": "1.4.0",
        "uptime_seconds": round(uptime, 2),
    }

