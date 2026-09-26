from datetime import datetime
from pydantic import BaseModel, ConfigDict


class IngestionMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str            # Config-assigned source identifier
    transport: str            # "file" | "stdin" | "tcp" | "http"
    source_address: str | None = None   # IP:port for network sources
    source_hint: str | None = None      # Explicit extension_id override (from config or HTTP header)
    received_at: datetime               # UTC wall-clock time of ingestion
    ingestion_sequence: int             # Session-local monotonic counter starting at 0
