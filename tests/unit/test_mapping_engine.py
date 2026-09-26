from pathlib import Path
from ulpf.mapping.mapping_engine import (
    MappingEngine,
    apply_type_coercion,
    parse_timestamp_to_epoch_ms,
)
from ulpf.mapping.profile import ActivityRule, MappingProfile, TimestampConfig
from ulpf.models.extracted import ExtractedFields


def test_type_coercion():
    assert apply_type_coercion("123", "int") == 123
    assert apply_type_coercion("123.45", "float") == 123.45
    assert apply_type_coercion(123, "str") == "123"
    assert apply_type_coercion("true", "bool") is True
    assert apply_type_coercion("1", "bool") is True
    assert apply_type_coercion("false", "bool") is False
    assert apply_type_coercion("invalid", "int") == "invalid"  # Graceful fallback


def test_timestamp_parsing():
    formats = ["%b %d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]
    # BSD syslog timestamp (without year, should use current year)
    ms = parse_timestamp_to_epoch_ms("Sep 01 12:30:05", formats)
    assert ms is not None
    assert ms > 0

    # ISO timestamp
    iso_ms = parse_timestamp_to_epoch_ms("2026-09-01T12:30:05+0000", formats)
    assert iso_ms is not None
    assert iso_ms > 0

    # None or unparseable
    assert parse_timestamp_to_epoch_ms(None, formats) is None
    assert parse_timestamp_to_epoch_ms("gibberish", formats) is None


def test_mapping_engine_load_profiles(tmp_path: Path):
    engine = MappingEngine()
    mappings_dir = Path("config/mappings")
    engine.load_directory(mappings_dir)

    assert engine.get_profile("syslog_generic") is not None
    assert engine.get_profile("cisco_asa") is not None
    assert engine.get_profile("cef_standard") is not None
    assert engine.get_profile("json_generic") is not None
    assert engine.get_profile("generic_passthrough") is not None


def test_mapping_engine_field_mapping_and_unmapped():
    engine = MappingEngine()
    engine.load_directory(Path("config/mappings"))
    profile = engine.get_profile("syslog_generic")
    assert profile is not None

    extracted = ExtractedFields(
        extension_id="syslog",
        extension_version="1.0.0",
        fields={
            "src": "192.168.1.100",
            "dst": "10.0.0.1",
            "spt": "54321",
            "dpt": "443",
            "proto": "TCP",
            "action": "deny",
            "custom_vendor_field": "extra_val",
        },
        timestamp_raw="Sep 01 12:30:05",
        parse_confidence=1.0,
    )

    ocsf, unmapped = engine.map(extracted, profile)

    # Mapped fields
    assert ocsf["src_endpoint.ip"] == "192.168.1.100"
    assert ocsf["dst_endpoint.ip"] == "10.0.0.1"
    assert ocsf["src_endpoint.port"] == 54321  # Coerced to int
    assert ocsf["dst_endpoint.port"] == 443    # Coerced to int
    assert ocsf["connection_info.protocol_name"] == "TCP"

    # Activity rules evaluation
    assert ocsf.get("activity_id") == 3      # Reset (denied)
    assert ocsf.get("action_id") == 2        # Denied
    assert ocsf.get("disposition_id") == 2   # Blocked
    assert ocsf.get("severity_id") == 3      # Medium

    # Timestamp
    assert "time" in ocsf
    assert ocsf["time"] > 0
    assert ocsf["metadata.original_time"] == "Sep 01 12:30:05"

    # Observer log name
    assert ocsf["metadata.log_name"] == "syslog"

    # Unmapped fields
    assert "custom_vendor_field" in unmapped
    assert unmapped["custom_vendor_field"] == "extra_val"
    assert "src" not in unmapped
