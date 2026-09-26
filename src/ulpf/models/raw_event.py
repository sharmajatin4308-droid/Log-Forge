import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
from .ingestion import IngestionMeta


class RawEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_event_id: str               # UUID4 string assigned at ingestion; never changes
    payload: str                    # Original event as UTF-8 text, character-for-character
    payload_encoding: str = "utf-8" # "utf-8" or "utf-8-replace" if lossy decoding occurred
    ingestion: IngestionMeta
