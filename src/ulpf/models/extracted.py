from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ExtractedFields(BaseModel):
    model_config = ConfigDict(frozen=True)

    extension_id: str                                  # Which extension produced this
    extension_version: str                              # Extension version used
    fields: dict[str, Any] = Field(default_factory=dict)# Vendor-native key-value pairs (NEVER OCSF names)
    timestamp_raw: str | None = None                    # Raw timestamp string extracted from payload (before normalization)
    parse_confidence: float = 1.0                       # 0.0–1.0; < 0.5 → partial status in pipeline
    mapping_profile_hint: str | None = None             # Extension may suggest a profile ID; core may override
