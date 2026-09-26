import json
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.path.insert(0, "src")
sys.path.insert(0, ".")

from ulpf.config.settings import Settings
from ulpf.models.ingestion import IngestionMeta
from ulpf.models.raw_event import RawEvent
from ulpf.pipeline.factory import create_pipeline

fixtures_dir = Path("tests/regression/fixtures")
fixtures_dir.mkdir(parents=True, exist_ok=True)

pipeline = create_pipeline(Settings(), output_mode="stdout")

sample_files = {
    "syslog_expected_001.json": "samples/syslog/sample_001.log",
    "cef_expected_001.json": "samples/cef/sample_001.log",
    "json_expected_001.json": "samples/json/sample_001.jsonl",
    "cisco_asa_expected_001.json": "samples/cisco_asa/sample_001.log",
}

for fixture_name, sample_path in sample_files.items():
    with open(sample_path, "r", encoding="utf-8") as f:
        line = f.readline().strip()
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
    data = record.model_dump(mode="json")
    # Normalize variable timing and metadata for regression testing
    data["ulpf_metadata"]["raw_event_id"] = "fixture-static-uuid"
    data["ulpf_metadata"]["processed_at"] = "2026-09-01T12:00:00Z"
    data["ulpf_metadata"]["processing_duration_ms"] = 0.5
    data["ocsf_event"]["metadata"]["uid"] = "fixture-static-uuid"

    out_file = fixtures_dir / fixture_name
    with open(out_file, "w", encoding="utf-8") as out:
        json.dump(data, out, indent=2)
    print(f"Generated fixture {out_file}")
