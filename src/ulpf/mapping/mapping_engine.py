from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Any

from .profile import MappingProfile
from .profile_loader import load_profile_from_yaml
from ..models.extracted import ExtractedFields

logger = logging.getLogger(__name__)


def apply_type_coercion(value: Any, target_type: str | None) -> Any:
    if value is None or target_type is None:
        return value
    try:
        match target_type.lower():
            case "int":
                return int(value)
            case "float":
                return float(value)
            case "str":
                return str(value)
            case "bool":
                if isinstance(value, bool):
                    return value
                s = str(value).lower()
                return s in ("true", "1", "yes", "t")
            case _:
                return value
    except (ValueError, TypeError):
        return value


_MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

_CACHED_YEAR: int = datetime.now(timezone.utc).year
_LAST_YEAR_CHECK: float = 0.0


def _get_current_year() -> int:
    global _CACHED_YEAR, _LAST_YEAR_CHECK
    now_m = time.monotonic()
    if now_m - _LAST_YEAR_CHECK > 3600.0:
        _CACHED_YEAR = datetime.now(timezone.utc).year
        _LAST_YEAR_CHECK = now_m
    return _CACHED_YEAR


def _parse_bsd_syslog_fast(raw_str: str, year: int) -> int | None:
    """Fast non-regex parser for BSD syslog timestamps (%b %d %H:%M:%S)."""
    parts = raw_str.split()
    if len(parts) != 3:
        return None
    month_name, day_str, time_str = parts
    month = _MONTH_MAP.get(month_name)
    if month is None:
        return None
    try:
        day = int(day_str)
        if not (1 <= day <= 31):
            return None
        t_parts = time_str.split(":")
        if len(t_parts) != 3:
            return None
        hour = int(t_parts[0])
        minute = int(t_parts[1])
        second = int(t_parts[2])
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 60):
            return None
        dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_timestamp_to_epoch_ms(raw_ts: str | None, formats: list[str]) -> int | None:
    if not raw_ts:
        return None
    raw_str = str(raw_ts).strip()
    current_year = _get_current_year()

    # Fast path for frequent BSD syslog timestamps
    if any(fmt in ("%b %d %H:%M:%S", "%b  %d %H:%M:%S") for fmt in formats):
        fast_result = _parse_bsd_syslog_fast(raw_str, current_year)
        if fast_result is not None:
            return fast_result

    for fmt in formats:
        try:
            dt = datetime.strptime(raw_str, fmt)
            if "%Y" not in fmt and "%y" not in fmt:
                dt = dt.replace(year=current_year)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except (ValueError, TypeError):
            continue

    # Fallback to ISO format parsing
    try:
        dt = datetime.fromisoformat(raw_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        pass

    return None



class MappingEngine:
    def __init__(self) -> None:
        self._profiles: dict[str, MappingProfile] = {}

    def load_profile(self, yaml_path: Path) -> MappingProfile:
        """Load a YAML mapping profile. Cache by profile_id. Return the profile."""
        profile = load_profile_from_yaml(yaml_path)
        self._profiles[profile.profile_id] = profile
        return profile

    def load_directory(self, dir_path: Path) -> None:
        """Load all .yaml files in a directory as mapping profiles."""
        if not dir_path.exists():
            return
        for file_path in dir_path.glob("*.yaml"):
            self.load_profile(file_path)

    def get_profile(self, profile_id: str) -> MappingProfile | None:
        return self._profiles.get(profile_id)

    def map(
        self,
        extracted: ExtractedFields,
        profile: MappingProfile,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Returns (ocsf_fields, unmapped_fields).
        ocsf_fields: dotted-path OCSF field names → values
        unmapped_fields: vendor field names → values (all extracted fields not in field_mappings)
        Never raises. Any error → log warning + add to unmapped.
        """
        ocsf: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}

        for vendor_field, value in extracted.fields.items():
            ocsf_path = profile.field_mappings.get(vendor_field)
            if ocsf_path:
                coerced = apply_type_coercion(value, profile.type_coercions.get(ocsf_path))
                ocsf[ocsf_path] = coerced
            else:
                unmapped[vendor_field] = value

        # Timestamp normalization
        if profile.timestamp_config:
            raw_ts = (
                extracted.timestamp_raw
                or ocsf.get(profile.timestamp_config.source_field)
                or extracted.fields.get(profile.timestamp_config.source_field)
            )
            epoch_ms = parse_timestamp_to_epoch_ms(raw_ts, profile.timestamp_config.formats)
            if epoch_ms is not None:
                ocsf["time"] = epoch_ms
                ocsf["metadata.original_time"] = raw_ts
            else:
                if raw_ts is not None:
                    logger.debug("Failed to parse timestamp '%s'", raw_ts)
                ocsf["time"] = 0

        # Activity rules (first matching rule wins)
        for rule in profile.activity_rules:
            vendor_val = extracted.fields.get(rule.condition_field)
            # Check intermediate field if present
            if vendor_val is None:
                for k, v in ocsf.items():
                    if k.startswith("_") and rule.condition_field in k:
                        vendor_val = v
                        break

            if vendor_val is not None and str(vendor_val) in rule.condition_values:
                ocsf["activity_id"] = rule.activity_id
                if rule.action_id is not None:
                    ocsf["action_id"] = rule.action_id
                if rule.disposition_id is not None:
                    ocsf["disposition_id"] = rule.disposition_id
                ocsf["severity_id"] = rule.severity_id
                break

        # Observer log_name
        if profile.observer_log_name:
            ocsf["metadata.log_name"] = profile.observer_log_name

        return ocsf, unmapped
