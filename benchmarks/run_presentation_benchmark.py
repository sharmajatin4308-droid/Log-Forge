"""
LogForge Official Presentation Benchmark Suite
Compares 1 Worker vs 4 Workers vs 8 Workers on a fixed 10,000-event multi-format security log dataset.

Rules:
- Uses actual LogForge pipeline without mocks or source modifications.
- Monotonic high-resolution timing (time.perf_counter).
- Fixed deterministic dataset (samples/benchmark_10k_mixed.log).
- Real persistence (JSONLConnector) with post-run verification.
- Warm-up run + 3 measured repetitions per configuration.
"""
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc

# Ensure paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))
sys.path.insert(0, str(WORKSPACE_ROOT))

from ulpf.config.settings import Settings, _detect_physical_cores
from ulpf.ingestion.file_source import FileIngestionSource
from ulpf.models.ocsf.network_activity import OCSFNetworkActivity
from ulpf.output.jsonl_connector import JSONLConnector
from ulpf.pipeline.factory import create_pipeline


def run_single_benchmark_pass(
    corpus_path: Path,
    workers: int,
    run_label: str,
    is_warmup: bool,
    batch_size: int = 100,
    output_dir: Path | None = None,
) -> dict:
    if output_dir is None:
        output_dir = WORKSPACE_ROOT / "output" / "benchmarks"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"bench_output_{workers}w_{run_label.lower().replace('-', '_')}.jsonl"

    # Verify no stale output exists
    if out_file.exists():
        out_file.unlink(missing_ok=True)
    assert not out_file.exists(), f"Stale output file {out_file} could not be removed"

    settings = Settings.load()
    source = FileIngestionSource(file_path=corpus_path)
    connector = JSONLConnector(output_path=out_file, flush_interval_records=100)

    pipeline = create_pipeline(settings, source=source, output_mode="stdout")
    pipeline.connector = connector

    tracemalloc.start()
    bench_start = time.perf_counter()
    cpu_start = time.process_time()

    # Execute actual LogForge pipeline
    stats = pipeline.run_parallel(
        max_workers=workers,
        executor_type="process",
        batch_size=batch_size,
    )
    if pipeline.connector is not None:
        pipeline.connector.close()

    wall_time = time.perf_counter() - bench_start
    cpu_time = time.process_time() - cpu_start
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    cpu_util_pct = (cpu_time / wall_time) * 100.0 if wall_time > 0 else 0.0
    throughput = stats.success / wall_time if wall_time > 0 else 0.0

    # Verification of persistence file
    assert out_file.exists(), f"Output file {out_file} was not created"
    
    unique_ids = set()
    latencies_ms = []
    line_count = 0
    schema_valid_count = 0
    raw_hash_valid_count = 0
    raw_data_match_count = 0

    with open(out_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line_count += 1
            record = json.loads(line)
            
            # 1. Unique ID
            raw_meta = record["raw_event"]
            ev_id = raw_meta["raw_event_id"]
            unique_ids.add(ev_id)

            # 2. Latency
            dur = record["ulpf_metadata"]["processing_duration_ms"]
            latencies_ms.append(dur)

            # 3. Raw payload hash check
            expected_hash = hashlib.sha256(raw_meta["payload"].encode("utf-8")).hexdigest()
            if record["ulpf_metadata"]["raw_payload_hash"] == expected_hash:
                raw_hash_valid_count += 1

            # 4. Raw payload preservation in OCSF event
            if record["ocsf_event"]["raw_data"] == raw_meta["payload"]:
                raw_data_match_count += 1

            # 5. Schema validation (sample 100 events per run for speed, or all)
            if idx < 500:
                try:
                    OCSFNetworkActivity.model_validate(record["ocsf_event"])
                    schema_valid_count += 1
                except Exception as e:
                    print(f"Validation failure at line {idx}: {e}")

    latencies_ms.sort()
    avg_latency = statistics.mean(latencies_ms) if latencies_ms else 0.0
    p50_latency = latencies_ms[int(len(latencies_ms) * 0.50)] if latencies_ms else 0.0
    p90_latency = latencies_ms[int(len(latencies_ms) * 0.90)] if latencies_ms else 0.0
    p95_latency = latencies_ms[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0
    p99_latency = latencies_ms[int(len(latencies_ms) * 0.99)] if latencies_ms else 0.0

    # Correctness Assertions
    expected_count = 10000
    assert stats.total == expected_count, f"Expected {expected_count} events, got {stats.total}"
    assert stats.success == expected_count, f"Expected {expected_count} success, got {stats.success}"
    assert stats.failed == 0, f"Expected 0 failed, got {stats.failed}"
    assert line_count == expected_count, f"Output line count {line_count} != {expected_count}"
    assert len(unique_ids) == expected_count, f"Duplicate events detected: {len(unique_ids)} unique vs {expected_count} total"
    assert raw_hash_valid_count == expected_count, f"Raw payload hash mismatch on {expected_count - raw_hash_valid_count} events"
    assert raw_data_match_count == expected_count, f"Raw payload data mismatch on {expected_count - raw_data_match_count} events"
    assert schema_valid_count == 500, f"OCSF validation failed on {500 - schema_valid_count} checked records"

    file_size_bytes = out_file.stat().st_size
    # Clean up output file after verification to save space
    out_file.unlink(missing_ok=True)

    return {
        "run_label": run_label,
        "is_warmup": is_warmup,
        "workers": workers,
        "input_events": expected_count,
        "success_events": stats.success,
        "failed_events": stats.failed,
        "output_records": line_count,
        "unique_events": len(unique_ids),
        "lost_events": expected_count - line_count,
        "duplicate_events": expected_count - len(unique_ids),
        "elapsed_sec": round(wall_time, 4),
        "cpu_time_sec": round(cpu_time, 4),
        "cpu_util_pct": round(cpu_util_pct, 2),
        "throughput_eps": round(throughput, 2),
        "avg_latency_ms": round(avg_latency, 4),
        "p50_latency_ms": round(p50_latency, 4),
        "p90_latency_ms": round(p90_latency, 4),
        "p95_latency_ms": round(p95_latency, 4),
        "p99_latency_ms": round(p99_latency, 4),
        "peak_memory_mb": round(peak_mb, 2),
        "output_file_size_bytes": file_size_bytes,
        "schema_valid": True,
        "raw_preservation_valid": True,
        "error_count": 0,
        "error_details": None,
    }


def main():
    corpus = WORKSPACE_ROOT / "samples" / "benchmark_10k_mixed.log"
    assert corpus.exists(), f"Corpus {corpus} not found! Run scripts/generate_benchmark_10k_mixed.py first."

    machine_env = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "processor": platform.processor(),
        "logical_cores": os.cpu_count(),
        "physical_cores": _detect_physical_cores(),
    }

    print("=" * 70)
    print("LOGFORGE OFFICIAL BENCHMARK SUITE: 1 vs 4 vs 8 WORKERS")
    print(f"Environment: {machine_env['os']} | Python {machine_env['python']}")
    print(f"CPU: {machine_env['processor']} ({machine_env['physical_cores']} physical cores, {machine_env['logical_cores']} logical)")
    print(f"Corpus: {corpus.name} ({corpus.stat().st_size:,} bytes, 10,000 mixed events)")
    print("=" * 70)

    worker_configs = [1, 4, 8]
    all_raw_results = []

    for w in worker_configs:
        print(f"\n---> Testing Configuration: {w} Worker{'s' if w > 1 else ''} (ProcessPoolExecutor, batch=100) <---")
        
        # Warm-up run
        print(f"  [Warmup-1] Running...", end="", flush=True)
        warmup_res = run_single_benchmark_pass(corpus, workers=w, run_label="Warmup-1", is_warmup=True)
        all_raw_results.append(warmup_res)
        print(f" Done. Elapsed: {warmup_res['elapsed_sec']:.3f}s | Throughput: {warmup_res['throughput_eps']:,.1f} EPS")

        # 3 Measured repetitions
        for rep in range(1, 4):
            label = f"Rep-{rep}"
            print(f"  [{label}] Running...", end="", flush=True)
            res = run_single_benchmark_pass(corpus, workers=w, run_label=label, is_warmup=False)
            all_raw_results.append(res)
            print(f" Done. Elapsed: {res['elapsed_sec']:.3f}s | Throughput: {res['throughput_eps']:,.1f} EPS | AvgLat: {res['avg_latency_ms']:.3f}ms | P95: {res['p95_latency_ms']:.3f}ms")

    # Also test sequential baseline (workers=1, pipeline.run()) for complete clarity
    print(f"\n---> Testing Baseline: 1 Worker Sequential (pipeline.run(), no executor) <---")
    print("  [Warmup-1] Running...", end="", flush=True)
    # Sequential helper
    def run_sequential_pass(run_label: str, is_warmup: bool):
        out_file = WORKSPACE_ROOT / "output" / "benchmarks" / f"bench_output_seq_{run_label.lower()}.jsonl"
        out_file.unlink(missing_ok=True)
        settings = Settings.load()
        source = FileIngestionSource(file_path=corpus)
        connector = JSONLConnector(output_path=out_file, flush_interval_records=100)
        pipeline = create_pipeline(settings, source=source, output_mode="stdout")
        pipeline.connector = connector
        tracemalloc.start()
        bench_start = time.perf_counter()
        cpu_start = time.process_time()
        stats = pipeline.run()
        pipeline.connector.close()
        wall_time = time.perf_counter() - bench_start
        cpu_time = time.process_time() - cpu_start
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        out_file.unlink(missing_ok=True)
        throughput = stats.success / wall_time
        return {
            "run_label": run_label,
            "is_warmup": is_warmup,
            "workers": 1,
            "model": "sequential_run",
            "input_events": stats.total,
            "success_events": stats.success,
            "failed_events": stats.failed,
            "elapsed_sec": round(wall_time, 4),
            "throughput_eps": round(throughput, 2),
            "peak_memory_mb": round(peak / (1024 * 1024), 2),
        }
    
    seq_warmup = run_sequential_pass("Warmup-1", True)
    print(f" Done. Elapsed: {seq_warmup['elapsed_sec']:.3f}s | Throughput: {seq_warmup['throughput_eps']:,.1f} EPS")
    seq_reps = []
    for rep in range(1, 4):
        label = f"Rep-{rep}"
        print(f"  [{label}] Running...", end="", flush=True)
        s_res = run_sequential_pass(label, False)
        seq_reps.append(s_res)
        print(f" Done. Elapsed: {s_res['elapsed_sec']:.3f}s | Throughput: {s_res['throughput_eps']:,.1f} EPS")

    # Aggregations
    aggregated = {}
    for w in worker_configs:
        reps = [r for r in all_raw_results if r["workers"] == w and not r["is_warmup"]]
        eps_values = [r["throughput_eps"] for r in reps]
        time_values = [r["elapsed_sec"] for r in reps]
        lat_values = [r["avg_latency_ms"] for r in reps]
        p95_values = [r["p95_latency_ms"] for r in reps]
        mem_values = [r["peak_memory_mb"] for r in reps]

        aggregated[w] = {
            "workers": w,
            "repetitions": len(reps),
            "mean_throughput_eps": round(statistics.mean(eps_values), 2),
            "std_throughput_eps": round(statistics.stdev(eps_values), 2) if len(eps_values) > 1 else 0.0,
            "min_throughput_eps": round(min(eps_values), 2),
            "max_throughput_eps": round(max(eps_values), 2),
            "mean_elapsed_sec": round(statistics.mean(time_values), 4),
            "std_elapsed_sec": round(statistics.stdev(time_values), 4) if len(time_values) > 1 else 0.0,
            "min_elapsed_sec": round(min(time_values), 4),
            "max_elapsed_sec": round(max(time_values), 4),
            "mean_avg_latency_ms": round(statistics.mean(lat_values), 4),
            "mean_p95_latency_ms": round(statistics.mean(p95_values), 4),
            "mean_peak_memory_mb": round(statistics.mean(mem_values), 2),
        }

    seq_eps_values = [r["throughput_eps"] for r in seq_reps]
    seq_time_values = [r["elapsed_sec"] for r in seq_reps]
    aggregated["sequential"] = {
        "workers": 1,
        "model": "sequential_run",
        "mean_throughput_eps": round(statistics.mean(seq_eps_values), 2),
        "mean_elapsed_sec": round(statistics.mean(seq_time_values), 4),
    }

    output_summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": machine_env,
        "corpus": {
            "path": str(corpus),
            "name": corpus.name,
            "size_bytes": corpus.stat().st_size,
            "event_count": 10000,
            "formats": {"syslog": 2500, "cef": 2500, "cisco_asa": 2500, "json": 2500},
        },
        "pipeline_config": {
            "batch_size": 100,
            "executor_type": "process",
            "output_connector": "JSONLConnector",
            "persistence": "enabled_disk_jsonl",
        },
        "raw_results": all_raw_results,
        "sequential_baseline_results": seq_reps,
        "aggregated_results": aggregated,
    }

    out_json = WORKSPACE_ROOT / "benchmarks" / "benchmark_1_4_8_workers_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(output_summary, f, indent=2)

    print("\n" + "=" * 70)
    print(f"BENCHMARK COMPLETED SUCCESSFULLY. Results saved to: {out_json}")
    print("=" * 70)


if __name__ == "__main__":
    main()
