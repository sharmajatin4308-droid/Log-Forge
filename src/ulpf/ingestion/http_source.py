from datetime import datetime, timezone
import uuid
from ..models.ingestion import IngestionMeta
from ..models.raw_event import RawEvent


def create_raw_event_from_http(
    payload: str,
    source_hint: str | None = None,
    source_address: str | None = None,
    source_id: str = "http",
    sequence: int = 0,
) -> RawEvent:
    """Helper adapter to convert HTTP request payload into a canonical RawEvent."""
    return RawEvent(
        raw_event_id=str(uuid.uuid4()),
        payload=payload,
        payload_encoding="utf-8",
        ingestion=IngestionMeta(
            source_id=source_id,
            transport="http",
            source_address=source_address,
            source_hint=source_hint,
            received_at=datetime.now(timezone.utc),
            ingestion_sequence=sequence,
        ),
    )
