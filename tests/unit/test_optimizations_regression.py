from pathlib import Path
import pytest
from typer.testing import CliRunner

from ulpf.config.settings import Settings, get_recommended_workers
from ulpf.pipeline.pipeline import Pipeline
from ulpf.cli.cli import app

runner = CliRunner()


def test_p0_a_default_executor_is_process():
    """Verify settings defaults to executor_type='process' and get_recommended_workers detects physical cores."""
    settings = Settings.load()
    assert settings.pipeline.executor_type == "process"
    rec_workers = get_recommended_workers("process")
    assert rec_workers >= 1


def test_p0_a_explicit_thread_executor_preserved():
    """Verify ThreadPoolExecutor remains functional when explicitly selected."""
    from ulpf.pipeline.factory import create_pipeline
    settings = Settings.load()
    sample_file = Path("samples/syslog/sample_001.log")
    pipeline = create_pipeline(settings, source_path=sample_file, output_mode="stdout")
    pipeline.connector = None
    stats = pipeline.run_parallel(max_workers=2, executor_type="thread")
    assert stats.total > 0
    assert stats.failed == 0


def test_p0_b_and_p1_a_all_hints_and_metadata_caching():
    """Verify all_hints and get_metadata return cached instances and update on dynamic registration."""
    from ulpf.registry.extension_registry import ExtensionRegistry
    from tests.unit.test_extension_registry import DummyExtensionA, DummyExtensionB

    reg = ExtensionRegistry()
    ext_a = DummyExtensionA()
    ext_b = DummyExtensionB()

    reg.register(ext_a)
    hints_1 = reg.all_hints()
    hints_2 = reg.all_hints()
    assert hints_1 == hints_2
    assert len(hints_1) == 1
    assert hints_1[0][0] == "dummy-a"

    # Register ext_b with priority 10 (higher priority than 20)
    reg.register(ext_b)
    hints_after = reg.all_hints()
    assert len(hints_after) == 2
    assert hints_after[0][0] == "dummy-b"
    assert hints_after[0][1].priority == 10
    assert hints_after[1][0] == "dummy-a"
    assert hints_after[1][1].priority == 20

    # Verify cached metadata
    meta_a = reg.get_metadata("dummy-a")
    meta_b = reg.get_metadata("dummy-b")
    assert meta_a is not None and meta_a.extension_id == "dummy-a"
    assert meta_b is not None and meta_b.extension_id == "dummy-b"
    assert reg.get_metadata("nonexistent") is None


def test_p0_c_fast_timestamp_parsing_correctness_and_edge_cases():
    """Verify fast path BSD parsing matches strptime and handles leap year, boundaries, and fallbacks."""
    from datetime import datetime, timezone
    from ulpf.mapping.mapping_engine import parse_timestamp_to_epoch_ms, _parse_bsd_syslog_fast, _get_current_year

    formats = ["%b %d %H:%M:%S", "%b  %d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]
    current_year = _get_current_year()

    # 1. Standard BSD syslog format
    ts_str = "Sep 01 12:30:05"
    expected = int(datetime(current_year, 9, 1, 12, 30, 5, tzinfo=timezone.utc).timestamp() * 1000)
    assert parse_timestamp_to_epoch_ms(ts_str, formats) == expected

    # 2. Double-space BSD syslog format
    ts_str_dbl = "Sep  1 12:30:05"
    assert parse_timestamp_to_epoch_ms(ts_str_dbl, formats) == expected

    # 3. Single digit day with single space
    ts_str_sgl = "Sep 1 12:30:05"
    assert parse_timestamp_to_epoch_ms(ts_str_sgl, formats) == expected

    # 4. Leap year verification
    # Feb 29 in leap year 2024 is valid
    assert _parse_bsd_syslog_fast("Feb 29 12:00:00", 2024) == int(datetime(2024, 2, 29, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    # Feb 29 in non-leap year 2026 is invalid and must return None
    assert _parse_bsd_syslog_fast("Feb 29 12:00:00", 2026) is None

    # 5. Invalid date bounds
    assert _parse_bsd_syslog_fast("Feb 30 12:00:00", 2024) is None
    assert _parse_bsd_syslog_fast("Apr 31 12:00:00", 2024) is None
    assert _parse_bsd_syslog_fast("Foo 01 12:00:00", 2024) is None
    assert _parse_bsd_syslog_fast("Sep 01 25:00:00", 2024) is None
    assert _parse_bsd_syslog_fast("Sep 01 12:60:00", 2024) is None
    assert _parse_bsd_syslog_fast("Sep 01 12:00:61", 2024) is None

    # 6. Fallback to ISO format
    iso_str = "2026-09-01T12:30:05+00:00"
    iso_expected = int(datetime(2026, 9, 1, 12, 30, 5, tzinfo=timezone.utc).timestamp() * 1000)
    assert parse_timestamp_to_epoch_ms(iso_str, formats) == iso_expected

    # 7. Empty and None inputs
    assert parse_timestamp_to_epoch_ms(None, formats) is None
    assert parse_timestamp_to_epoch_ms("", formats) is None
    assert parse_timestamp_to_epoch_ms("   ", formats) is None

    # 8. Unparseable string returns None gracefully
    assert parse_timestamp_to_epoch_ms("NOT_A_TIMESTAMP", formats) is None


def test_p1_b_static_ocsf_product_reuse():
    """Verify OCSFProduct is reused and identical across assembled events."""
    from ulpf.ocsf.assembler import OCSFAssembler, DEFAULT_OCSF_PRODUCT
    from ulpf.models.raw_event import RawEvent
    from ulpf.models.ingestion import IngestionMeta
    from ulpf.models.extracted import ExtractedFields
    from ulpf.mapping.profile import MappingProfile
    from datetime import datetime, timezone

    assembler = OCSFAssembler()
    profile = MappingProfile(
        profile_id="test",
        profile_version="1.0",
        format_id="test",
        vendor=None,
        product=None,
        field_mappings={},
        type_coercions={},
        timestamp_config=None,
        activity_rules=[],
        observer_log_name="test",
    )
    raw = RawEvent(
        raw_event_id="e1",
        payload="test",
        ingestion=IngestionMeta(
            source_id="test",
            transport="file",
            received_at=datetime.now(timezone.utc),
            ingestion_sequence=1,
        ),
    )
    extracted = ExtractedFields(extension_id="test", extension_version="1.0", fields={})
    ev1, _ = assembler.assemble(raw, extracted, profile, {}, {}, [], datetime.now(timezone.utc))
    ev2, _ = assembler.assemble(raw, extracted, profile, {}, {}, [], datetime.now(timezone.utc))

    assert ev1.metadata.product is DEFAULT_OCSF_PRODUCT
    assert ev2.metadata.product is DEFAULT_OCSF_PRODUCT
    assert ev1.metadata.product.name == "LogForge"


def test_p1_c_jsonl_connector_size_tracking(tmp_path: Path):
    """Verify JSONLConnector tracks file size in memory and triggers rotation correctly."""
    from ulpf.output.jsonl_connector import JSONLConnector
    from tests.unit.test_parallel_pipeline import _make_dummy_record

    out_file = tmp_path / "size_track.jsonl"
    connector = JSONLConnector(
        output_path=out_file,
        flush_interval_records=2,
        flush_interval_seconds=10.0,
        max_file_size_mb=1,
    )
    rec = _make_dummy_record(1)
    connector.write(rec)
    connector.write(rec)
    assert connector._current_file_size > 0
    connector.flush()
    connector.close()

    # Verify rotation with max_file_size_mb=0
    rot_file = tmp_path / "rot_track.jsonl"
    rot_conn = JSONLConnector(output_path=rot_file, max_file_size_mb=0)
    rot_conn.write(rec)
    rot_conn.close()
    # At least one rotated file should exist
    rotated_files = list(tmp_path.glob("rot_track_*.jsonl"))
    assert len(rotated_files) >= 1



def test_p1_d_stdout_connector_unlocked_flush(monkeypatch):
    """Verify StdoutConnector flushes outside critical lock without deadlock or contention."""
    import io
    from ulpf.output.stdout_connector import StdoutConnector
    from tests.unit.test_parallel_pipeline import _make_dummy_record

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    conn = StdoutConnector(pretty=False)
    rec = _make_dummy_record(1)
    conn.write(rec)
    assert len(buf.getvalue().strip().splitlines()) == 1


def test_p1_e_payload_size_protection_boundaries_and_lossless_preservation():
    """Verify max_payload_bytes guard, boundary conditions, and lossless preservation of oversized payloads."""
    from ulpf.pipeline.factory import create_pipeline
    from ulpf.models.raw_event import RawEvent
    from ulpf.models.ingestion import IngestionMeta
    from datetime import datetime, timezone

    settings = Settings.load()
    pipeline = create_pipeline(settings, output_mode="stdout")
    pipeline.connector = None
    # Configure small limit for testing boundaries: exactly 100 bytes
    pipeline.max_payload_bytes = 100

    # 1. Below limit (99 bytes) -> succeeds normally
    payload_99 = "<134>Sep 01 12:30:05 fw01 action=allow src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP msg=" + ("X" * (99 - 85))
    assert len(payload_99.encode("utf-8")) == 99
    raw_below = RawEvent(
        raw_event_id="below-1",
        payload=payload_99,
        ingestion=IngestionMeta(source_id="test", transport="file", received_at=datetime.now(timezone.utc), ingestion_sequence=1),
    )
    rec_below = pipeline.process_one(raw_below)
    assert rec_below.ulpf_metadata.parse_status == "success"
    assert rec_below.raw_event.payload == payload_99

    # 2. Exactly at limit (100 bytes) -> succeeds normally
    payload_100 = "<134>Sep 01 12:30:05 fw01 action=allow src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP msg=" + ("X" * (100 - 85))
    assert len(payload_100.encode("utf-8")) == 100
    raw_exact = RawEvent(
        raw_event_id="exact-1",
        payload=payload_100,
        ingestion=IngestionMeta(source_id="test", transport="file", received_at=datetime.now(timezone.utc), ingestion_sequence=2),
    )
    rec_exact = pipeline.process_one(raw_exact)
    assert rec_exact.ulpf_metadata.parse_status == "success"
    assert rec_exact.raw_event.payload == payload_100

    # 3. Over limit (101 bytes) -> parse_status='failed', but lossless preservation
    payload_101 = "<134>Sep 01 12:30:05 fw01 action=allow src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP msg=" + ("X" * (101 - 85))
    assert len(payload_101.encode("utf-8")) == 101
    raw_over = RawEvent(
        raw_event_id="over-1",
        payload=payload_101,
        ingestion=IngestionMeta(source_id="test", transport="file", received_at=datetime.now(timezone.utc), ingestion_sequence=3),
    )
    rec_over = pipeline.process_one(raw_over)
    assert rec_over.ulpf_metadata.parse_status == "failed"
    assert any("exceeds max_payload_bytes" in err for err in rec_over.ulpf_metadata.parse_errors)
    # CRITICAL: Lossless raw event preservation
    assert rec_over.raw_event.payload == payload_101
    assert rec_over.ocsf_event["raw_data"] == payload_101
    assert rec_over.ulpf_metadata.extension_id == "syslog"
    assert rec_over.ocsf_event["class_uid"] == 4001


def test_p2_a_max_in_flight_batches_config_and_validation():
    """Verify max_in_flight_batches validation and pipeline propagation."""
    from pydantic import ValidationError
    from ulpf.config.settings import PipelineConfig

    cfg = PipelineConfig(max_in_flight_batches=5)
    assert cfg.max_in_flight_batches == 5

    with pytest.raises(ValidationError):
        PipelineConfig(max_in_flight_batches=-1)


def test_p2_b_large_batch_warning_logged(caplog, tmp_path: Path):
    """Verify warning is emitted when batch_size > 500 and workers > 4 in process mode."""
    import logging
    from ulpf.pipeline.factory import create_pipeline

    in_file = tmp_path / "warn_input.log"
    in_file.write_text("<134>Sep 01 12:30:00 fw01 action=allow\n", encoding="utf-8")
    settings = Settings.load()
    pipeline = create_pipeline(settings, source_path=in_file, output_mode="stdout")
    pipeline.connector = None

    with caplog.at_level(logging.WARNING):
        pipeline.run_parallel(max_workers=5, executor_type="process", batch_size=1000)

    assert any("Large batch_size" in record.message for record in caplog.records)


def test_p2_c_precompiled_syslog_regex():
    """Verify compiled SYSLOG_PRI_REGEX matches valid priorities and rejects invalid."""
    from extensions.syslog_ext.parser import SyslogExtension
    from ulpf.models.raw_event import RawEvent
    from ulpf.models.ingestion import IngestionMeta
    from datetime import datetime, timezone

    ext = SyslogExtension()
    make_raw = lambda payload: RawEvent(
        raw_event_id="1", payload=payload,
        ingestion=IngestionMeta(source_id="test", transport="file", received_at=datetime.now(timezone.utc), ingestion_sequence=1)
    )

    assert ext.can_process(make_raw("<134>Sep 01 12:30:00 fw01 test")) is True
    assert ext.can_process(make_raw("<0>Sep 01 12:30:00 fw01 test")) is True
    assert ext.can_process(make_raw("<191>Sep 01 12:30:00 fw01 test")) is True
    assert ext.can_process(make_raw("Sep 01 12:30:00 fw01 test")) is False
    assert ext.can_process(make_raw("CEF:0|Vendor|Product|1.0|...")) is False
    assert ext.can_process(make_raw("")) is False






