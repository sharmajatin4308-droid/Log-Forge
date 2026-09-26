"""
Comprehensive final benchmark suite for LogForge optimization verification.
Tests:
1. Microbenchmarks (all_hints, metadata, timestamp, JSONL write, can_process, process_one)
2. Worker scaling: 1, 2, 4, 8, 16 workers (Process and Thread)
3. Batch size scaling: 50, 100, 200, 500, 1000 batches
4. JSONL disk output end-to-end
"""
import json
import os
from pathlib import Path
import platform
import sys
import time
import tracemalloc

# Ensure paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))
sys.path.insert(0, str(WORKSPACE_ROOT))

from ulpf.config.settings import Settings
from ulpf.ingestion.file_source import FileIngestionSource
from ulpf.models import IngestionMeta, RawEvent
from ulpf.output.jsonl_connector import JSONLConnector
from ulpf.pipeline.factory import create_pipeline
from ulpf.mapping.mapping_engine import parse_timestamp_to_epoch_ms
from extensions.syslog_ext.parser import SyslogExtension


class NoOpConnector:
    def write(self, record): pass
    def flush(self): pass
    def close(self): pass


def run_microbenchmarks():
    print("\n" + "=" * 60)
    print("RUNNING MICROBENCHMARKS")
    print("=" * 60)
    settings = Settings.load()
    pipeline = create_pipeline(settings, output_mode="stdout")
    pipeline.connector = NoOpConnector()

    # 1. all_hints()
    n_hints = 200_000
    t0 = time.perf_counter()
    for _ in range(n_hints):
        pipeline.registry.all_hints()
    all_hints_lat_us = ((time.perf_counter() - t0) / n_hints) * 1_000_000
    print(f"all_hints() latency: {all_hints_lat_us:.3f} µs/call")

    # 2. extension_metadata()
    syslog_ext = pipeline.registry.get("syslog")
    n_meta = 200_000
    t0 = time.perf_counter()
    for _ in range(n_meta):
        syslog_ext.extension_metadata()
    meta_lat_us = ((time.perf_counter() - t0) / n_meta) * 1_000_000
    print(f"extension_metadata() latency: {meta_lat_us:.3f} µs/call")

    # 3. parse_timestamp_to_epoch_ms()
    n_ts = 100_000
    ts_str = "Oct 11 22:14:15"
    fmts = ["%b %d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"]
    t0 = time.perf_counter()
    for _ in range(n_ts):
        parse_timestamp_to_epoch_ms(ts_str, fmts)
    ts_lat_us = ((time.perf_counter() - t0) / n_ts) * 1_000_000
    print(f"parse_timestamp_to_epoch_ms(BSD syslog) latency: {ts_lat_us:.3f} µs/call")

    # 4. can_process()
    from datetime import datetime, timezone

    raw_ev = RawEvent(
        raw_event_id="test-1",
        payload="<34>1 2023-10-11T22:14:15.003Z host myapp 1234 - - test message",
        ingestion=IngestionMeta(
            source_id="test",
            transport="file",
            received_at=datetime.now(timezone.utc),
            ingestion_sequence=1,
        ),
    )
    n_can = 100_000
    t0 = time.perf_counter()
    for _ in range(n_can):
        syslog_ext.can_process(raw_ev)
    can_lat_us = ((time.perf_counter() - t0) / n_can) * 1_000_000
    print(f"SyslogExtension.can_process() latency: {can_lat_us:.3f} µs/call")

    # 5. JSONLConnector.write()
    test_rec = pipeline.process_one(raw_ev)
    test_out = WORKSPACE_ROOT / "benchmarks" / "temp_micro_out.jsonl"
    if test_out.exists():
        test_out.unlink()
    conn = JSONLConnector(test_out, flush_interval_records=1000)
    n_writes = 20_000
    t0 = time.perf_counter()
    for _ in range(n_writes):
        conn.write(test_rec)
    conn.flush()
    conn.close()
    write_lat_us = ((time.perf_counter() - t0) / n_writes) * 1_000_000
    if test_out.exists():
        test_out.unlink()
    print(f"JSONLConnector.write() latency: {write_lat_us:.3f} µs/write")

    # 6. process_one() end-to-end
    n_p1 = 20_000
    t0 = time.perf_counter()
    for _ in range(n_p1):
        pipeline.process_one(raw_ev)
    p1_lat_us = ((time.perf_counter() - t0) / n_p1) * 1_000_000
    p1_eps = 1_000_000.0 / p1_lat_us
    print(f"process_one() latency: {p1_lat_us:.3f} µs/event ({p1_eps:.1f} EPS)")

    return {
        "all_hints_us": all_hints_lat_us,
        "metadata_us": meta_lat_us,
        "timestamp_us": ts_lat_us,
        "can_process_us": can_lat_us,
        "jsonl_write_us": write_lat_us,
        "process_one_us": p1_lat_us,
        "process_one_eps": p1_eps,
    }


def run_scaling_benchmark(corpus_path: Path, worker_list: list[int], executor_types: list[str], batch_size: int = 100):
    print("\n" + "=" * 60)
    print(f"RUNNING WORKER SCALING BENCHMARKS on {corpus_path.name}")
    print("=" * 60)
    results = {}

    for ex_type in executor_types:
        results[ex_type] = {}
        for w in worker_list:
            source = FileIngestionSource(file_path=corpus_path)
            settings = Settings.load()
            pipeline = create_pipeline(settings, source=source, output_mode="stdout")
            pipeline.connector = NoOpConnector()

            tracemalloc.start()
            t0 = time.monotonic()
            stats = pipeline.run_parallel(
                max_workers=w,
                batch_size=batch_size,
                executor_type=ex_type,
            )
            elapsed = time.monotonic() - t0
            _cur, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            eps = stats.total / elapsed if elapsed > 0 else 0
            peak_mb = peak / (1024 * 1024)
            print(f"[{ex_type.upper():7s}] Workers={w:2d} | Time={elapsed:6.2f}s | EPS={eps:8.1f} | Total={stats.total} (Success={stats.success}) | PeakMem={peak_mb:5.1f} MB")
            results[ex_type][str(w)] = {
                "workers": w,
                "executor": ex_type,
                "elapsed_sec": round(elapsed, 3),
                "eps": round(eps, 1),
                "peak_mb": round(peak_mb, 2),
                "total": stats.total,
                "success": stats.success,
            }

    return results


def run_batch_size_benchmark(corpus_path: Path, batch_sizes: list[int], workers: int = 8):
    print("\n" + "=" * 60)
    print(f"RUNNING BATCH SIZE BENCHMARKS (Workers={workers}) on {corpus_path.name}")
    print("=" * 60)
    results = {}

    for bs in batch_sizes:
        source = FileIngestionSource(file_path=corpus_path)
        settings = Settings.load()
        pipeline = create_pipeline(settings, source=source, output_mode="stdout")
        pipeline.connector = NoOpConnector()

        tracemalloc.start()
        t0 = time.monotonic()
        stats = pipeline.run_parallel(
            max_workers=workers,
            batch_size=bs,
            executor_type="process",
        )
        elapsed = time.monotonic() - t0
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        eps = stats.total / elapsed if elapsed > 0 else 0
        peak_mb = peak / (1024 * 1024)
        print(f"BatchSize={bs:4d} | Time={elapsed:6.2f}s | EPS={eps:8.1f} | PeakMem={peak_mb:5.1f} MB")
        results[str(bs)] = {
            "batch_size": bs,
            "workers": workers,
            "elapsed_sec": round(elapsed, 3),
            "eps": round(eps, 1),
            "peak_mb": round(peak_mb, 2),
            "total": stats.total,
            "success": stats.success,
        }

    return results


def run_jsonl_output_benchmark(corpus_path: Path, workers: int = 8, batch_size: int = 100):
    print("\n" + "=" * 60)
    print(f"RUNNING JSONL DISK OUTPUT BENCHMARK (Workers={workers}, Batch={batch_size})")
    print("=" * 60)
    out_file = WORKSPACE_ROOT / "benchmarks" / "benchmark_run_output.jsonl"
    if out_file.exists():
        out_file.unlink()

    source = FileIngestionSource(file_path=corpus_path)
    settings = Settings.load()
    conn = JSONLConnector(output_path=out_file, flush_interval_records=500)
    pipeline = create_pipeline(settings, source=source, output_mode="stdout")
    pipeline.connector = conn

    tracemalloc.start()
    t0 = time.monotonic()
    stats = pipeline.run_parallel(
        max_workers=workers,
        batch_size=batch_size,
        executor_type="process",
    )
    conn.flush()
    conn.close()
    elapsed = time.monotonic() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    eps = stats.total / elapsed if elapsed > 0 else 0
    peak_mb = peak / (1024 * 1024)

    # Count output lines and verify
    line_count = 0
    with open(out_file, "r", encoding="utf-8") as f:
        for _ in f:
            line_count += 1
    file_size_mb = out_file.stat().st_size / (1024 * 1024)
    out_file.unlink()

    print(f"JSONL Output | Time={elapsed:6.2f}s | EPS={eps:8.1f} | Lines={line_count} | Size={file_size_mb:.1f} MB | PeakMem={peak_mb:5.1f} MB")
    return {
        "workers": workers,
        "batch_size": batch_size,
        "elapsed_sec": round(elapsed, 3),
        "eps": round(eps, 1),
        "lines_written": line_count,
        "peak_mb": round(peak_mb, 2),
    }


def main():
    corpus = WORKSPACE_ROOT / "samples" / "syslog" / "benchmark_100k.log"
    assert corpus.exists(), f"Corpus {corpus} missing!"

    summary = {
        "platform": {
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or "Unknown CPU"),
            "logical_cores": os.cpu_count(),
        },
        "microbenchmarks": run_microbenchmarks(),
        "worker_scaling": run_scaling_benchmark(
            corpus,
            worker_list=[1, 2, 4, 8, 16],
            executor_types=["process", "thread"],
            batch_size=100,
        ),
        "batch_scaling": run_batch_size_benchmark(
            corpus,
            batch_sizes=[50, 100, 200, 500, 1000],
            workers=8,
        ),
        "jsonl_disk_benchmark": run_jsonl_output_benchmark(
            corpus,
            workers=8,
            batch_size=100,
        ),
    }

    out_path = WORKSPACE_ROOT / "benchmarks" / "final_benchmark_measured.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved all measured results to {out_path}")


if __name__ == "__main__":
    main()
