from pydantic import BaseModel, ConfigDict


class ExtensionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    extension_id: str               # Unique, kebab-case: "syslog", "cisco-asa", "cef", "json", "generic"
    extension_version: str          # SemVer: "1.0.0"
    format_id: str                  # Format family: "syslog", "cef", "json", "cisco_asa", "unknown"
    vendor: str | None = None       # "Cisco", "ArcSight", None for generic formats
    product: str | None = None      # "ASA", "CEF", None
    author: str = "LogForge"
    default_mapping_profile: str    # Profile ID to use when not overridden
    description: str = ""
