from pathlib import Path
from typing import Any
import yaml

from .profile import ActivityRule, MappingProfile, TimestampConfig


def load_profile_from_yaml(yaml_path: Path) -> MappingProfile:
    """Load a single YAML file and return a MappingProfile instance."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    return load_profile_from_dict(data)


def load_profile_from_dict(data: dict[str, Any]) -> MappingProfile:
    """Instantiate a MappingProfile from a dictionary."""
    ts_data = data.get("timestamp")
    ts_config = None
    if ts_data and isinstance(ts_data, dict):
        ts_config = TimestampConfig(
            source_field=ts_data.get("source_field", "timestamp_raw"),
            formats=list(ts_data.get("formats", [])),
        )

    rules_data = data.get("activity_rules", []) or []
    activity_rules = []
    for r in rules_data:
        activity_rules.append(
            ActivityRule(
                condition_field=r["condition_field"],
                condition_values=[str(v) for v in r.get("condition_values", [])],
                activity_id=int(r.get("activity_id", 0)),
                action_id=int(r["action_id"]) if r.get("action_id") is not None else None,
                disposition_id=int(r["disposition_id"]) if r.get("disposition_id") is not None else None,
                severity_id=int(r.get("severity_id", 0)),
            )
        )

    return MappingProfile(
        profile_id=str(data["profile_id"]),
        profile_version=str(data.get("profile_version", "1.0")),
        format_id=str(data.get("format_id", "unknown")),
        vendor=data.get("vendor"),
        product=data.get("product"),
        field_mappings=dict(data.get("field_mappings") or {}),
        type_coercions=dict(data.get("type_coercions") or {}),
        timestamp_config=ts_config,
        activity_rules=activity_rules,
        observer_log_name=data.get("observer_log_name"),
    )
