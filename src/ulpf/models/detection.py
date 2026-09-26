from pydantic import BaseModel, ConfigDict, Field


class DetectionHints(BaseModel):
    model_config = ConfigDict(frozen=True)

    extension_id: str                                  # Must exactly match ExtensionMetadata.extension_id
    prefixes: list[str] = Field(default_factory=list)  # Byte-strings matched against payload[:len(prefix)]
    contains: list[str] = Field(default_factory=list)  # Substrings checked in payload[:300]
    transports: list[str] = Field(default_factory=list)# Compatible transports (empty = all)
    priority: int = 100                                # Lower = checked first (10=vendor-specific, 50=generic format, 100=fallback)
