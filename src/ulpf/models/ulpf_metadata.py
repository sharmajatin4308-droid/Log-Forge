from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ULPFMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Lineage
    raw_event_id: str                   # Links to RawEvent.raw_event_id
    extension_id: str                   # Which extension parsed this event
    extension_version: str              # Extension version
    mapping_profile_id: str             # MappingProfile used
    mapping_profile_version: str        # Profile version
    schema_version: str = "1.4.0"       # OCSF schema version

    # Processing status
    parse_status: Literal["success", "partial", "failed"]
    parse_errors: list[str] = Field(default_factory=list)  # Human-readable error messages; empty list if clean

    # Timing
    processed_at: datetime              # UTC wall-clock time when this event was processed
    processing_duration_ms: float       # Wall-clock milliseconds for this event

    # Source
    source_hint_used: str | None = None # The source_hint that was active, if any
    transport: str                      # Transport from IngestionMeta

    # Integrity
    # Hex-encoded SHA-256 hash of preserved UTF-8 payload representation.
    # Note: If ingestion performed lossy decoding (payload_encoding='utf-8-replace'),
    # this hashes the preserved text representation, not the pre-decoded input bytes.
    raw_payload_hash: str | None = None
