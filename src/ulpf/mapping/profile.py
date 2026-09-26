from dataclasses import dataclass, field


@dataclass(frozen=True)
class TimestampConfig:
    source_field: str           # Vendor field name containing the raw timestamp
    formats: list[str]          # strptime format strings, tried in order


@dataclass(frozen=True)
class ActivityRule:
    condition_field: str        # Vendor field to check (e.g., "action")
    condition_values: list[str] # Values that match (e.g., ["deny", "DENY", "drop"])
    activity_id: int            # OCSF activity_id to set
    action_id: int | None       # OCSF action_id to set (None = don't set)
    disposition_id: int | None  # OCSF disposition_id to set (None = don't set)
    severity_id: int = 0        # OCSF severity_id to set


@dataclass(frozen=True)
class MappingProfile:
    profile_id: str
    profile_version: str
    format_id: str
    vendor: str | None
    product: str | None

    field_mappings: dict[str, str]          # vendor_field → ocsf_path (dotted, e.g. "src_endpoint.ip")
    type_coercions: dict[str, str]          # ocsf_path → "int"|"float"|"str"|"bool"
    timestamp_config: TimestampConfig | None

    activity_rules: list[ActivityRule] = field(default_factory=list)
    observer_log_name: str | None = None    # Sets metadata.log_name
