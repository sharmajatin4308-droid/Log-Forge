import json
from pathlib import Path
import threading
import time
import tracemalloc
import uuid
from datetime import datetime, timezone

import pytest

from ulpf.config.settings import Settings
from ulpf.ingestion.file_source import FileIngestionSource
from ulpf.models.ingestion import IngestionMeta
from ulpf.models.ocsf.metadata import OCSFMetadata, OCSFProduct
from ulpf.models.ocsf.network_activity import OCSFNetworkActivity
from ulpf.models.raw_event import RawEvent
from ulpf.models.ulpf_metadata import ULPFMetadata
from ulpf.models.ulpf_record import ULPFRecord
from ulpf.output.jsonl_connector import JSONLConnector
from ulpf.output.stdout_connector import StdoutConnector
from ulpf.pipeline.factory import create_pipeline


def _make_dummy_record(seq: int) -> ULPFRecord:
    raw = RawEvent(
        raw_event_id=str(uuid.uuid4()),
        payload=f"<134>Sep 01 12:30:{seq % 60:02d} fw01 action=allow src=10.0.0.{seq % 250 + 1} dst=8.8.8.8 dpt=53 proto=UDP",
        ingestion=IngestionMeta(
            source_id="test_suite",
            transport="file",
            received_at=datetime.now(timezone.utc),
            ingestion_sequence=seq,
        ),
    )
    ocsf_meta = OCSFMetadata(
        version="1.4.0",
        product=OCSFProduct(name="LogForge", vendor_name="Hacked", version="1.0.0"),
        uid=raw.raw_event_id,
    )
    ocsf_ev = OCSFNetworkActivity(
        class_uid=4001,
        class_name="Network Activity",
        category_uid=4,
        category_name="Network Activity",
        activity_id=1,
        type_uid=400101,
        time=int(time.time()),
        severity_id=1,
        raw_data=raw.payload,
        metadata=ocsf_meta,
    )
    ulpf_meta = ULPFMetadata(
        raw_event_id=raw.raw_event_id,
        extension_id="syslog",
        extension_version="1.0.0",
        mapping_profile_id="syslog_generic",
        mapping_profile_version="1.0.0",
        schema_version="1.4.0",
        parse_status="success",
        parse_errors=[],
        processed_at=datetime.now(timezone.utc),
        processing_duration_ms=0.5,
        source_hint_used=None,
        transport="file",
    )
    return ULPFRecord(
        ocsf_event=ocsf_ev.model_dump(exclude_none=True),
        ulpf_metadata=ulpf_meta,
        raw_event=raw,
    )


def test_jsonl_connector_thread_safety(tmp_path: Path):
    """10 threads x 100 records -> exactly 1,000 valid JSON lines in output file."""
    out_file = tmp_path / "concurrent.jsonl"
    connector = JSONLConnector(output_path=out_file, flush_interval_records=50)

    num_threads = 10
    records_per_thread = 100

    def worker(thread_idx: int):
        for i in range(records_per_thread):
            rec = _make_dummy_record(thread_idx * 1000 + i)
            connector.write(rec)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    connector.close()

    lines = out_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == num_threads * records_per_thread

    for line_idx, line in enumerate(lines):
        parsed = json.loads(line)
        assert "ocsf_event" in parsed
        assert "ulpf_metadata" in parsed
        assert "raw_event" in parsed


def test_stdout_connector_thread_safety(capsys):
    """10 threads x 50 records -> exactly 500 complete valid JSON lines."""
    connector = StdoutConnector(pretty=False)
    num_threads = 10
    records_per_thread = 50

    def worker(thread_idx: int):
        for i in range(records_per_thread):
            rec = _make_dummy_record(thread_idx * 1000 + i)
            connector.write(rec)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    connector.flush()
    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.strip().splitlines() if ln.strip()]
    assert len(lines) == num_threads * records_per_thread
    for line in lines:
        data = json.loads(line)
        assert "ocsf_event" in data


def test_run_parallel_produces_same_records_as_sequential(tmp_path: Path):
    """Feed identical input to run() and run_parallel(workers=4). Assert identical records and parse status."""
    log_content = "\n".join(
        f"<134>Sep 01 12:30:{i % 60:02d} host{i % 5} action=deny src=10.0.0.{i % 250 + 1} dst=8.8.8.8 dpt={i + 10} proto=UDP"
        for i in range(100)
    )
    in_file = tmp_path / "input.log"
    in_file.write_text(log_content + "\n", encoding="utf-8")

    out_seq = tmp_path / "seq.jsonl"
    out_par = tmp_path / "par.jsonl"

    settings = Settings.load()

    # Sequential run
    p_seq = create_pipeline(settings, source_path=in_file, output_path=out_seq)
    stats_seq = p_seq.run()

    # Parallel run
    p_par = create_pipeline(settings, source_path=in_file, output_path=out_par)
    stats_par = p_par.run_parallel(max_workers=4)

    assert stats_seq.total == 100
    assert stats_par.total == 100
    assert stats_seq.success == stats_par.success
    assert stats_seq.partial == stats_par.partial
    assert stats_seq.failed == stats_par.failed

    seq_lines = [json.loads(line) for line in out_seq.read_text(encoding="utf-8").strip().splitlines()]
    par_lines = [json.loads(line) for line in out_par.read_text(encoding="utf-8").strip().splitlines()]

    assert len(seq_lines) == 100
    assert len(par_lines) == 100

    # Index by raw_event payload
    seq_by_payload = {rec["raw_event"]["payload"]: rec for rec in seq_lines}
    par_by_payload = {rec["raw_event"]["payload"]: rec for rec in par_lines}

    assert set(seq_by_payload.keys()) == set(par_by_payload.keys())

    for payload, s_rec in seq_by_payload.items():
        p_rec = par_by_payload[payload]
        assert s_rec["ulpf_metadata"]["parse_status"] == p_rec["ulpf_metadata"]["parse_status"]
        assert s_rec["ulpf_metadata"]["extension_id"] == p_rec["ulpf_metadata"]["extension_id"]
        assert s_rec["ulpf_metadata"]["mapping_profile_id"] == p_rec["ulpf_metadata"]["mapping_profile_id"]
        # ocsf event fields (excluding metadata.uid / duration / timestamps)
        s_ocsf = s_rec["ocsf_event"]
        p_ocsf = p_rec["ocsf_event"]
        assert s_ocsf["class_uid"] == p_ocsf["class_uid"]
        assert s_ocsf["raw_data"] == p_ocsf["raw_data"]


def test_run_parallel_workers_1_matches_sequential(tmp_path: Path):
    """run_parallel(max_workers=1) produces semantically equivalent output to run()."""
    in_file = tmp_path / "w1_input.log"
    in_file.write_text(
        "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP\n"
        "<134>Sep 01 12:30:06 fw01 action=allow src=10.0.0.5 dst=1.1.1.1 dpt=443 proto=TCP\n",
        encoding="utf-8",
    )
    out_seq = tmp_path / "w1_seq.jsonl"
    out_par = tmp_path / "w1_par.jsonl"

    settings = Settings.load()
    p_seq = create_pipeline(settings, source_path=in_file, output_path=out_seq)
    stats_seq = p_seq.run()

    p_par = create_pipeline(settings, source_path=in_file, output_path=out_par)
    stats_par = p_par.run_parallel(max_workers=1)

    assert stats_seq.total == stats_par.total == 2
    assert stats_seq.success == stats_par.success == 2


@pytest.mark.parametrize("workers", [1, 2, 4, 8])
def test_run_parallel_no_events_lost(tmp_path: Path, workers: int):
    """Feed N events, assert stats.total == N for workers in {1, 2, 4, 8}."""
    n_events = 40
    lines = [f"<134>Sep 01 12:30:00 fw01 msg=test_{i} src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP" for i in range(n_events)]
    in_file = tmp_path / f"lost_test_w{workers}.log"
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_file = tmp_path / f"lost_test_w{workers}.jsonl"

    settings = Settings.load()
    p = create_pipeline(settings, source_path=in_file, output_path=out_file)
    stats = p.run_parallel(max_workers=workers)

    assert stats.total == n_events
    written_lines = [ln for ln in out_file.read_text(encoding="utf-8").strip().splitlines() if ln.strip()]
    assert len(written_lines) == n_events


def test_run_parallel_no_duplicate_events(tmp_path: Path):
    """Assert len(set(raw_event_ids)) == stats.total."""
    n_events = 60
    lines = [f"<134>Sep 01 12:30:00 fw01 msg=dup_test_{i} src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP" for i in range(n_events)]
    in_file = tmp_path / "dup_input.log"
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_file = tmp_path / "dup_output.jsonl"

    settings = Settings.load()
    p = create_pipeline(settings, source_path=in_file, output_path=out_file)
    stats = p.run_parallel(max_workers=4)

    written_lines = [json.loads(ln) for ln in out_file.read_text(encoding="utf-8").strip().splitlines()]
    assert len(written_lines) == stats.total == n_events

    raw_event_ids = [rec["raw_event"]["raw_event_id"] for rec in written_lines]
    assert len(raw_event_ids) == len(set(raw_event_ids)) == n_events


def test_run_parallel_error_records_preserved(tmp_path: Path):
    """Include malformed events. Assert stats.failed count matches sequential run."""
    lines = [
        "<134>Sep 01 12:30:00 fw01 action=deny src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP",
        "!!!THIS_IS_TOTALLY_CORRUPTED_GARBAGE_LINE_THAT_FAILS_EVERY_PARSER!!!",
        "<134>Sep 01 12:30:02 fw01 action=allow src=10.0.0.2 dst=8.8.8.8 dpt=80 proto=TCP",
    ]
    in_file = tmp_path / "err_input.log"
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    settings = Settings.load()
    out_seq = tmp_path / "err_seq.jsonl"
    out_par = tmp_path / "err_par.jsonl"

    p_seq = create_pipeline(settings, source_path=in_file, output_path=out_seq)
    stats_seq = p_seq.run()

    p_par = create_pipeline(settings, source_path=in_file, output_path=out_par)
    stats_par = p_par.run_parallel(max_workers=4)

    assert stats_seq.total == stats_par.total == 3
    assert stats_seq.failed == stats_par.failed
    assert stats_seq.success == stats_par.success
    assert stats_seq.partial == stats_par.partial


def test_run_parallel_raw_payload_invariant(tmp_path: Path):
    """Every output record's ocsf_event['raw_data'] equals raw_event.payload."""
    in_file = tmp_path / "payload_inv_input.log"
    lines = [f"<134>Sep 01 12:30:00 fw01 msg=inv_{i} src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP" for i in range(25)]
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_file = tmp_path / "payload_inv_out.jsonl"

    settings = Settings.load()
    p = create_pipeline(settings, source_path=in_file, output_path=out_file)
    p.run_parallel(max_workers=4)

    written_lines = [json.loads(ln) for ln in out_file.read_text(encoding="utf-8").strip().splitlines()]
    assert len(written_lines) == 25
    for rec in written_lines:
        assert rec["raw_event"]["payload"] == rec["ocsf_event"]["raw_data"]


def test_run_parallel_process_executor(tmp_path: Path):
    """Test run_parallel with executor_type='process'."""
    in_file = tmp_path / "proc_input.log"
    lines = [f"<134>Sep 01 12:30:00 fw01 msg=proc_{i} src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP" for i in range(30)]
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_file = tmp_path / "proc_out.jsonl"

    settings = Settings.load()
    p = create_pipeline(settings, source_path=in_file, output_path=out_file)
    stats = p.run_parallel(max_workers=2, executor_type="process")

    assert stats.total == 30
    assert stats.success == 30
    written = [json.loads(ln) for ln in out_file.read_text(encoding="utf-8").strip().splitlines()]
    assert len(written) == 30
    for rec in written:
        assert rec["raw_event"]["payload"] == rec["ocsf_event"]["raw_data"]


def test_run_parallel_memory_bounded(tmp_path: Path):
    """Process 1,000 events with workers=4. Assert tracemalloc peak < 50MB."""
    in_file = tmp_path / "mem_input.log"
    lines = [f"<134>Sep 01 12:30:{i%60:02d} fw01 msg=mem_{i} src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP" for i in range(1000)]
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_file = tmp_path / "mem_out.jsonl"

    settings = Settings.load()
    p = create_pipeline(settings, source_path=in_file, output_path=out_file)

    tracemalloc.start()
    stats = p.run_parallel(max_workers=4)
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    assert stats.total == 1000
    assert peak_mb < 50.0, f"Peak memory exceeded 50MB budget: {peak_mb:.2f} MB"


def test_process_batch_direct():
    """Verify pipeline.process_batch preserves event semantics and lineage."""
    settings = Settings.load()
    pipeline = create_pipeline(settings, output_mode="stdout")
    pipeline.connector = None

    raws = [
        RawEvent(
            raw_event_id=f"evt-{i}",
            payload=f"<134>Sep 01 12:30:00 fw01 msg=test_{i} src=10.0.0.{i+1} dst=8.8.8.8 dpt=53 proto=UDP",
            ingestion=IngestionMeta(
                source_id="test",
                transport="file",
                received_at=datetime.now(timezone.utc),
                ingestion_sequence=i,
            ),
        )
        for i in range(15)
    ]

    records = pipeline.process_batch(raws)
    assert len(records) == 15
    for i, rec in enumerate(records):
        assert rec.raw_event.raw_event_id == f"evt-{i}"
        assert rec.raw_event.payload == rec.ocsf_event["raw_data"]
        assert rec.ulpf_metadata.raw_event_id == f"evt-{i}"
        assert rec.ulpf_metadata.parse_status in ("success", "partial")


def test_batched_multiprocessing_boundaries_and_partial_batch(tmp_path: Path):
    """Test process mode with batch_size=50 on 127 events (2 full batches + 1 partial residual batch of 27)."""
    in_file = tmp_path / "batch_partial_input.log"
    total_events = 127
    batch_size = 50
    lines = [
        f"<134>Sep 01 12:30:{i%60:02d} fw01 batch_idx={i} src=10.0.0.{(i%250)+1} dst=8.8.8.8 dpt=53 proto=UDP"
        for i in range(total_events)
    ]
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_file = tmp_path / "batch_partial_out.jsonl"

    settings = Settings.load()
    p = create_pipeline(settings, source_path=in_file, output_path=out_file)
    stats = p.run_parallel(max_workers=2, executor_type="process", batch_size=batch_size)

    assert stats.total == total_events
    assert stats.success + stats.partial + stats.failed == total_events

    written = [json.loads(ln) for ln in out_file.read_text(encoding="utf-8").strip().splitlines()]
    assert len(written) == total_events

    # Verify no loss and no duplication
    raw_payloads = [r["raw_event"]["payload"] for r in written]
    assert len(raw_payloads) == total_events
    assert len(set(raw_payloads)) == total_events


def test_batched_multiprocessing_multiple_workers_and_sizes(tmp_path: Path):
    """Verify batched multiprocessing across multiple worker counts (2, 4) and batch sizes (10, 25)."""
    total_events = 100
    lines = [
        f"<134>Sep 01 12:30:{i%60:02d} fw01 seq={i} src=10.0.0.{(i%250)+1} dst=8.8.8.8 dpt=53 proto=UDP"
        for i in range(total_events)
    ]
    in_file = tmp_path / "multi_workers_input.log"
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    settings = Settings.load()

    for workers in [2, 4]:
        for b_size in [10, 25]:
            out_file = tmp_path / f"out_w{workers}_b{b_size}.jsonl"
            p = create_pipeline(settings, source_path=in_file, output_path=out_file)
            stats = p.run_parallel(max_workers=workers, executor_type="process", batch_size=b_size)

            assert stats.total == total_events
            written = [json.loads(ln) for ln in out_file.read_text(encoding="utf-8").strip().splitlines()]
            assert len(written) == total_events
            unique_ids = {r["raw_event"]["raw_event_id"] for r in written}
            assert len(unique_ids) == total_events


def test_sequential_thread_and_process_consistency(tmp_path: Path):
    """Verify sequential, thread-parallel, and batched process-parallel produce identical counts."""
    lines = [
        f"<134>Sep 01 12:30:{i%60:02d} fw01 msg=consist_{i} src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP"
        for i in range(60)
    ]
    lines.append("MALFORMED_LOG_EVENT_FOR_CONSISTENCY_TEST")
    in_file = tmp_path / "consist_input.log"
    in_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    settings = Settings.load()

    # 1. Sequential
    out_seq = tmp_path / "consist_seq.jsonl"
    p_seq = create_pipeline(settings, source_path=in_file, output_path=out_seq)
    stats_seq = p_seq.run()

    # 2. Thread parallel
    out_thr = tmp_path / "consist_thr.jsonl"
    p_thr = create_pipeline(settings, source_path=in_file, output_path=out_thr)
    stats_thr = p_thr.run_parallel(max_workers=2, executor_type="thread")

    # 3. Batched Process parallel
    out_prc = tmp_path / "consist_prc.jsonl"
    p_prc = create_pipeline(settings, source_path=in_file, output_path=out_prc)
    stats_prc = p_prc.run_parallel(max_workers=2, executor_type="process", batch_size=20)

    assert stats_seq.total == stats_thr.total == stats_prc.total == 61
    assert stats_seq.failed == stats_thr.failed == stats_prc.failed == 0
    assert stats_seq.success == stats_thr.success == stats_prc.success == 60
    assert stats_seq.partial == stats_thr.partial == stats_prc.partial == 1


def test_recommended_workers_auto_detection():
    """Verify get_recommended_workers returns physical core approximation (half logical)."""
    import os
    from ulpf.pipeline.pipeline import get_recommended_workers
    from ulpf.config.settings import get_recommended_workers as get_rec_settings

    expected = max(1, (os.cpu_count() or 2) // 2)
    assert get_recommended_workers("process") == expected
    assert get_rec_settings() == expected
    assert expected >= 1


