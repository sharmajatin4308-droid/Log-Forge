from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from ulpf.config.settings import Settings
from ulpf.models.ingestion import IngestionMeta
from ulpf.models.raw_event import RawEvent
from ulpf.pipeline.factory import create_pipeline


@pytest.mark.parametrize(
    "fixture_name,sample_path",
    [
        ("syslog_expected_001.json", "samples/syslog/sample_001.log"),
        ("cef_expected_001.json", "samples/cef/sample_001.log"),
        ("json_expected_001.json", "samples/json/sample_001.jsonl"),
        ("cisco_asa_expected_001.json", "samples/cisco_asa/sample_001.log"),
    ],
)
def test_regression_fixtures(fixture_name, sample_path):
    fixture_file = Path("tests/regression/fixtures") / fixture_name
    assert fixture_file.exists(), f"Missing fixture: {fixture_file}"

    with open(fixture_file, "r", encoding="utf-8") as f:
        expected = json.load(f)

    with open(sample_path, "r", encoding="utf-8") as f:
        line = f.readline().strip()

    pipeline = create_pipeline(Settings(), output_mode="stdout")
    raw = RawEvent(
        raw_event_id="fixture-static-uuid",
        payload=line,
        ingestion=IngestionMeta(
            source_id="test",
            transport="file",
            received_at=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
            ingestion_sequence=0,
        ),
    )
    record = pipeline.process_one(raw)
    actual = record.model_dump(mode="json")

    # Normalize variable timing and metadata for deterministic regression testing
    actual["ulpf_metadata"]["raw_event_id"] = "fixture-static-uuid"
    actual["ulpf_metadata"]["processed_at"] = "2026-09-01T12:00:00Z"
    actual["ulpf_metadata"]["processing_duration_ms"] = 0.5
    actual["ocsf_event"]["metadata"]["uid"] = "fixture-static-uuid"

    assert actual["ocsf_event"] == expected["ocsf_event"]
    assert actual["ulpf_metadata"]["extension_id"] == expected["ulpf_metadata"]["extension_id"]
    assert actual["ulpf_metadata"]["mapping_profile_id"] == expected["ulpf_metadata"]["mapping_profile_id"]
    assert actual["ulpf_metadata"]["parse_status"] == expected["ulpf_metadata"]["parse_status"]
    assert actual["raw_event"]["payload"] == expected["raw_event"]["payload"]
