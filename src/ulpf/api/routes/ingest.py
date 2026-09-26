import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...config.settings import Settings
from ...ingestion.http_source import create_raw_event_from_http
from ...models.pipeline import PipelineStats
from ...pipeline.factory import create_pipeline

router = APIRouter(tags=["Ingestion"])

# Global shared pipeline instance for API requests
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        settings = Settings.load()
        _pipeline = create_pipeline(settings, output_mode="jsonl")
    return _pipeline


def reset_pipeline():
    global _pipeline
    if _pipeline is not None:
        if getattr(_pipeline, "connector", None):
            try:
                _pipeline.connector.close()
            except Exception:
                pass
        _pipeline = None


class IngestRequest(BaseModel):
    payload: str
    source_hint: Optional[str] = None


class BatchIngestRequest(BaseModel):
    events: list[str] = Field(..., max_length=100)


@router.post("/ingest")
async def ingest_single(req: IngestRequest, request: Request):
    client_ip = request.client.host if request.client else None
    raw = create_raw_event_from_http(
        payload=req.payload,
        source_hint=req.source_hint,
        source_address=client_ip,
    )
    pipeline = get_pipeline()
    record = pipeline.process_one(raw)
    if pipeline.connector:
        pipeline.connector.flush()
    return record.model_dump(mode="json")



@router.post("/ingest/batch")
async def ingest_batch(req: BatchIngestRequest, request: Request):
    if len(req.events) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 events per batch")

    client_ip = request.client.host if request.client else None
    pipeline = get_pipeline()
    records = []
    stats = PipelineStats()
    start_ns = time.perf_counter_ns()

    for seq, line in enumerate(req.events):
        raw = create_raw_event_from_http(
            payload=line,
            source_address=client_ip,
            sequence=seq,
        )
        record = pipeline.process_one(raw)
        records.append(record.model_dump(mode="json"))
        stats.total += 1
        match record.ulpf_metadata.parse_status:
            case "success":
                stats.success += 1
            case "partial":
                stats.partial += 1
            case "failed":
                stats.failed += 1

    stats.total_duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
    if pipeline.connector:
        pipeline.connector.flush()

    return {
        "records": records,
        "stats": stats.model_dump(),
    }
