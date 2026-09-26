from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from ulpf.config.settings import Settings
from ulpf.models.extracted import ExtractedFields
from ulpf.models.raw_event import RawEvent
from ulpf.pipeline.factory import create_pipeline
from ulpf.pipeline.pipeline import _make_error_record, _get_passthrough_profile


from ulpf.models.ingestion import IngestionMeta


def _sample_raw(payload: str = "test payload line", source_hint: str | None = None) -> RawEvent:
    return RawEvent(
        raw_event_id="raw-1",
        payload=payload,
        ingestion=IngestionMeta(
            source_id="test",
            transport="file",
            source_hint=source_hint,
            received_at=datetime.now(timezone.utc),
            ingestion_sequence=0,
        ),
    )


def test_make_error_record():
    raw = _sample_raw("error sample line")
    rec = _make_error_record(raw, "Test error message", datetime.now(timezone.utc))
    assert rec.ocsf_event["class_uid"] == 4001
    assert rec.ocsf_event["raw_data"] == "error sample line"
    assert rec.ulpf_metadata.parse_status == "failed"
    assert "Test error message" in rec.ulpf_metadata.parse_errors


def test_get_passthrough_profile():
    prof = _get_passthrough_profile("unknown_ext")
    assert prof.profile_id == "generic_passthrough"
    assert prof.format_id == "unknown"


def test_pipeline_extension_parse_exception():
    settings = Settings.load()
    pipeline = create_pipeline(settings=settings)

    from ulpf.models.detection import DetectionHints

    # Mock an extension that raises an exception during parse
    mock_ext = MagicMock()
    mock_ext.extension_metadata.return_value.extension_id = "syslog"
    mock_ext.extension_metadata.return_value.extension_version = "1.0.0"
    mock_ext.extension_metadata.return_value.default_mapping_profile = "syslog_generic"
    mock_ext.detection_hints.return_value = DetectionHints(extension_id="syslog", priority=50)
    mock_ext.parse.side_effect = ValueError("Broken parser simulator")
    mock_ext.can_process.return_value = True

    pipeline.registry._extensions["syslog"] = mock_ext

    raw = _sample_raw("test payload line", source_hint="syslog")
    record = pipeline.process_one(raw)
    assert record.ulpf_metadata.parse_status == "failed"
    assert any("Broken parser simulator" in err for err in record.ulpf_metadata.parse_errors)


def test_pipeline_missing_mapping_profile():
    from ulpf.models.detection import DetectionHints

    settings = Settings.load()
    pipeline = create_pipeline(settings=settings)

    # Extracted fields point to non-existent mapping profile
    mock_ext = MagicMock()
    mock_ext.extension_metadata.return_value.extension_id = "syslog"
    mock_ext.extension_metadata.return_value.extension_version = "1.0.0"
    mock_ext.extension_metadata.return_value.default_mapping_profile = "non_existent_profile_xyz"
    mock_ext.detection_hints.return_value = DetectionHints(extension_id="syslog", priority=50)
    mock_ext.parse.return_value = ExtractedFields(
        extension_id="syslog",
        extension_version="1.0.0",
        fields={"src": "1.2.3.4"},
        parse_confidence=0.9,
    )
    mock_ext.can_process.return_value = True

    pipeline.registry._extensions["syslog"] = mock_ext

    raw = _sample_raw("test line", source_hint="syslog")
    record = pipeline.process_one(raw)
    assert record.ulpf_metadata.parse_status in ("partial", "success")
    assert any("Mapping profile not found" in err for err in record.ulpf_metadata.parse_errors)


def test_pipeline_run_with_source(tmp_path: Path):
    from ulpf.ingestion.file_source import FileIngestionSource

    test_file = tmp_path / "sample.log"
    test_file.write_text(
        "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP\n"
        "<110>Sep 01 12:31:10 fw01 action=allow src=192.168.1.5 dst=203.0.113.1 dpt=443 proto=TCP\n",
        encoding="utf-8",
    )

    settings = Settings.load()
    source = FileIngestionSource(file_path=test_file)
    pipeline = create_pipeline(settings=settings, source=source)

    stats = pipeline.run()
    assert stats.total == 2
    assert stats.success == 2
    assert stats.failed == 0
    assert stats.eps >= 0


def test_pipeline_raw_payload_hash_and_duration():
    import hashlib

    sample = "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP"
    raw = _sample_raw(sample, source_hint="syslog")
    pipeline = create_pipeline(Settings(), output_mode="stdout")

    record = pipeline.process_one(raw)
    expected_hash = hashlib.sha256(sample.encode("utf-8")).hexdigest()

    assert record.ulpf_metadata.raw_payload_hash == expected_hash
    assert record.ulpf_metadata.processing_duration_ms >= 0.0
    assert isinstance(record.ulpf_metadata.processing_duration_ms, float)

    # Test error record carries hash as well
    err_record = _make_error_record(raw, "simulated error", datetime.now(timezone.utc))
    assert err_record.ulpf_metadata.raw_payload_hash == expected_hash
    assert err_record.ulpf_metadata.processing_duration_ms >= 0.0

