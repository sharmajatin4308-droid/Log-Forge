import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from ...config.settings import Settings

router = APIRouter(tags=["Events"])

OUTPUT_FILE: Optional[Path] = None


def _get_output_path() -> Path:
    if OUTPUT_FILE is not None:
        return Path(OUTPUT_FILE)
    settings = Settings.load()
    return Path(settings.pipeline.output_dir) / "events.jsonl"


def _read_output_file() -> list[dict]:
    out_path = _get_output_path()
    if not out_path.exists():
        return []

    records = []
    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    return records


@router.get("/events")
async def list_events(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, pattern="^(success|partial|failed)$"),
):
    all_records = _read_output_file()
    # Reverse so newest events appear first
    all_records.reverse()

    if status:
        filtered = [
            r for r in all_records
            if r.get("ulpf_metadata", {}).get("parse_status") == status
        ]
    else:
        filtered = all_records

    total = len(filtered)
    page = filtered[offset : offset + limit]

    return {
        "records": page,
        "total": total,
    }


@router.get("/events/{raw_event_id}")
async def get_event_by_id(raw_event_id: str):
    all_records = _read_output_file()
    for r in all_records:
        if (
            r.get("ulpf_metadata", {}).get("raw_event_id") == raw_event_id
            or r.get("raw_event", {}).get("raw_event_id") == raw_event_id
        ):
            return r

    raise HTTPException(status_code=404, detail="Event not found")


@router.delete("/events")
async def clear_events():
    """
    Clears all stored events in the local events.jsonl output stream.
    Used for development/demo maintenance and testing cleanups.
    """
    from .ingest import reset_pipeline
    reset_pipeline()

    out_path = _get_output_path()
    count = 0

    if out_path.exists():
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to clear events: {e}")

    return {
        "status": "cleared",
        "deleted_count": count,
    }

