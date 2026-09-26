import argparse
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
    FIRST_COMPLETED,
)
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc

# Ensure paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ulpf.config.settings import Settings
from ulpf.ingestion.file_source import FileIngestionSource
from ulpf.output.jsonl_connector import JSONLConnector
from ulpf.pipeline.factory import create_pipeline


class NoOpConnector:
    def write(self, record): pass
    def flush(self): pass
    def close(self): pass


def run_one_benchmark_pass(
    file_path: Path,
    workers: int,
    executor_type: str,
    output_mode: str,  # "noop" or "jsonl"
    run_label: str,
    target_out_path: Path | None = None,
    batch_size: int = 100,
) -> dict:
    settings = Settings.load()
    source = FileIngestionSource(file_path=file_path)

    if output_mode == "noop":
        connector = NoOpConnector()
    else:
        assert target_out_path is not None
        if target_out_path.exists():
            target_out_path.unlink(missing_ok=True)
        connector = JSONLConnector(output_path=target_out_path, flush_interval_records=500)

    pipeline = create_pipeline(settings, source=source, output_mode="stdout")
    pipeline.connector = connector

    tracemalloc.start()
    latencies_ms: list[float] = []
    unique_ids: set[str] = set()
    total = 0
    success = 0
    partial = 0
    failed = 0

    bench_start = time.monotonic()
    cpu_start = time.process_time()

    if workers <= 1:
        for raw in source.events():
            t0 = time.perf_counter()
            rec = pipeline.process_one(raw)
            lat = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(lat)

            unique_ids.add(rec.raw_event.raw_event_id)
            total += 1
            st = rec.ulpf_metadata.parse_status
            if st == "success":
                success += 1
            elif st == "partial":
                partial += 1
            else:
                failed += 1
        if output_mode != "noop":
            connector.flush()
            connector.close()
    else:
        # In process mode, workers process with connector=None; main thread writes
        if executor_type == "process":
            pipeline.connector = None
            max_in_flight_batches = max(2, workers * 2)
            futures: dict = {}

            with ProcessPoolExecutor(max_workers=workers) as ex:
                source_iter = iter(source.events())
                source_exhausted = False

                while not source_exhausted or futures:
                    while not source_exhausted and len(futures) < max_in_flight_batches:
                        batch = []
                        try:
                            while len(batch) < batch_size:
                                batch.append(next(source_iter))
                        except StopIteration:
                            source_exhausted = True

                        if batch:
                            t0 = time.perf_counter()
                            f = ex.submit(pipeline.process_batch, batch)
                            futures[f] = (t0, len(batch))

                    if not futures:
                        break

                    done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
                    for f in done:
                        t0, batch_len = futures.pop(f)
                        batch_lat = (time.perf_counter() - t0) * 1000.0
                        amortized_lat = batch_lat / batch_len if batch_len > 0 else 0.0

                        batch_records = f.result()
                        for rec in batch_records:
                            latencies_ms.append(amortized_lat)
                            if output_mode != "noop":
                                connector.write(rec)

                            unique_ids.add(rec.raw_event.raw_event_id)
                            total += 1
                            st = rec.ulpf_metadata.parse_status
                            if st == "success":
                                success += 1
                            elif st == "partial":
                                partial += 1
                            else:
                                failed += 1
        else:
            max_in_flight = workers * 4
            futures: dict = {}

            with ThreadPoolExecutor(max_workers=workers) as ex:
                source_iter = iter(source.events())
                source_exhausted = False

                while not source_exhausted or futures:
                    while not source_exhausted and len(futures) < max_in_flight:
                        try:
                            raw = next(source_iter)
                            t0 = time.perf_counter()
                            f = ex.submit(pipeline.process_one, raw)
                            futures[f] = t0
                        except StopIteration:
                            source_exhausted = True

                    if not futures:
                        break

                    done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
                    for f in done:
                        t0 = futures.pop(f)
                        lat = (time.perf_counter() - t0) * 1000.0
                        latencies_ms.append(lat)

                        rec = f.result()
                        if output_mode != "noop":
                            pass  # threads write inside process_one via connector

                        unique_ids.add(rec.raw_event.raw_event_id)
                        total += 1
                        st = rec.ulpf_metadata.parse_status
                        if st == "success":
                            success += 1
                        elif st == "partial":
                            partial += 1
                        else:
                            failed += 1

        if output_mode != "noop":
            connector.flush()
            connector.close()

    wall_time = time.monotonic() - bench_start
    cpu_time = time.process_time() - cpu_start
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    eps = total / wall_time if wall_time > 0 else 0.0
    latencies_ms.sort()
    p50 = latencies_ms[int(len(latencies_ms) * 0.50)] if latencies_ms else 0.0
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)] if latencies_ms else 0.0
    peak_mb = peak / (1024 * 1024)
    cpu_util = (cpu_time / wall_time) * 100.0 if wall_time > 0 else 0.0

    # Verification checks
    assert total == 100_000, f"Expected exactly 100,000 events, got {total}"
    assert len(unique_ids) == 100_000, f"Expected 100,000 unique events, got {len(unique_ids)} (duplicates found)"
    assert success + partial + failed == 100_000

    verified_file_lines = None
    if output_mode != "noop" and target_out_path is not None:
        file_lines = 0
        file_uids = set()
        with open(target_out_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    file_lines += 1
                    data = json.loads(line)
                    file_uids.add(data["raw_event"]["raw_event_id"])
        assert file_lines == 100_000, f"Expected 100,000 file lines, got {file_lines}"
        assert len(file_uids) == 100_000, f"Expected 100,000 unique IDs in file, got {len(file_uids)}"
        verified_file_lines = file_lines
        # Cleanup file to save disk space
        target_out_path.unlink(missing_ok=True)

    result = {
        "run_label": run_label,
        "workers": workers,
        "executor_type": executor_type,
        "batch_size": batch_size,
        "output_mode": output_mode,
        "total": total,
        "unique_events": len(unique_ids),
        "verified_file_lines": verified_file_lines,
        "success": success,
        "partial": partial,
        "failed": failed,
        "wall_time": wall_time,
        "cpu_time": cpu_time,
        "cpu_util_pct": cpu_util,
        "eps": eps,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "peak_mb": peak_mb,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="LogForge Strong 100k Benchmark Suite")
    parser.add_argument("--corpus", type=Path, default=Path("samples/syslog/benchmark_100k.log"))
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--benchmarks", nargs="+", default=["A", "B"], choices=["A", "B"])
    parser.add_argument("--executors", nargs="+", default=["thread", "process"], choices=["thread", "process"])
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 4, 8, 16])
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for ProcessPoolExecutor (default: 100)")
    args = parser.parse_args()

    corpus_path = args.corpus
    if not corpus_path.exists():
        print(f"Error: Corpus {corpus_path} not found. Generating it now...")
        import subprocess
        subprocess.run([sys.executable, "scripts/generate_benchmark_100k.py"], check=True)

    results_file = Path("benchmarks/benchmark_100k_results.json")
    if results_file.exists():
        try:
            with open(results_file, "r", encoding="utf-8") as f:
                all_data = json.load(f)
            print(f"Loaded existing results from {results_file} ({len(all_data.get('runs', []))} past runs recorded)")
        except Exception:
            all_data = {
                "metadata": {
                    "platform": f"{platform.system()} {platform.release()}",
                    "python": platform.python_version(),
                    "cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or "Unknown CPU"),
                    "cores": os.cpu_count(),
                    "corpus": str(corpus_path),
                    "events_per_run": 100_000,
                    "warmup_runs": args.warmup,
                    "measured_reps": args.reps,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                "runs": [],
                "summaries": {},
            }
    else:
        all_data = {
            "metadata": {
                "platform": f"{platform.system()} {platform.release()}",
                "python": platform.python_version(),
                "cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or "Unknown CPU"),
                "cores": os.cpu_count(),
                "corpus": str(corpus_path),
                "events_per_run": 100_000,
                "warmup_runs": args.warmup,
                "measured_reps": args.reps,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "runs": [],
            "summaries": {},
        }


    print("=" * 100)
    print("LOGFORGE 100,000-EVENT BENCHMARK SUITE")
    print("=" * 100)
    print(f"Platform:    {all_data['metadata']['platform']}")
    print(f"Python:      {all_data['metadata']['python']}")
    print(f"Processor:   {all_data['metadata']['cpu']} ({all_data['metadata']['cores']} logical cores)")
    print(f"Corpus:      {corpus_path} (100,000 events)")
    print(f"Config:      {args.warmup} warm-up runs, {args.reps} measured repetitions per cell")
    print(f"Benchmarks:  {args.benchmarks}")
    print(f"Executors:   {args.executors}")
    print(f"Workers:     {args.workers}")
    print("=" * 100)
    print("")

    benchmarks_to_run = []
    if "A" in args.benchmarks:
        benchmarks_to_run.append(("Benchmark A (Processing-Only)", "noop"))
    if "B" in args.benchmarks:
        benchmarks_to_run.append(("Benchmark B (End-to-End JSONL)", "jsonl"))

    for bench_title, output_mode in benchmarks_to_run:
        print("\n" + "#" * 100)
        print(f"# STARTING {bench_title.upper()} (Output: {output_mode.upper()})")
        print("#" * 100)

        all_data["summaries"][output_mode] = {}

        for exec_type in args.executors:
            all_data["summaries"][output_mode][exec_type] = {}

            for w in args.workers:
                cfg_header = f"[{bench_title}] Executor: {exec_type.upper()} | Workers: {w}"
                print("\n" + "-" * 80)
                print(f"{cfg_header}")
                print("-" * 80)

                # Warmup runs
                for wu_idx in range(1, args.warmup + 1):
                    wu_label = f"Warmup-{wu_idx}"
                    print(f"  --> Running {wu_label}...", end=" ", flush=True)
                    out_path = Path(f"output/bench_{output_mode}_{exec_type}_w{w}_wu.jsonl") if output_mode != "noop" else None
                    wu_res = run_one_benchmark_pass(
                        file_path=corpus_path,
                        workers=w,
                        executor_type=exec_type,
                        output_mode=output_mode,
                        run_label=wu_label,
                        target_out_path=out_path,
                        batch_size=args.batch_size,
                    )
                    wu_res["is_warmup"] = True
                    all_data["runs"].append(wu_res)
                    print(f"Done in {wu_res['wall_time']:.2f}s ({wu_res['eps']:,.0f} EPS) [Discarded]", flush=True)

                # Measured repetitions
                measured_runs = []
                for rep_idx in range(1, args.reps + 1):
                    rep_label = f"Rep-{rep_idx}"
                    print(f"  --> Running {rep_label}...", end=" ", flush=True)
                    out_path = Path(f"output/bench_{output_mode}_{exec_type}_w{w}_rep{rep_idx}.jsonl") if output_mode != "noop" else None
                    m_res = run_one_benchmark_pass(
                        file_path=corpus_path,
                        workers=w,
                        executor_type=exec_type,
                        output_mode=output_mode,
                        run_label=rep_label,
                        target_out_path=out_path,
                        batch_size=args.batch_size,
                    )
                    m_res["is_warmup"] = False
                    measured_runs.append(m_res)
                    all_data["runs"].append(m_res)

                    print(
                        f"Done in {m_res['wall_time']:.2f}s | "
                        f"{m_res['eps']:,.0f} EPS | "
                        f"p50: {m_res['p50_ms']:.2f}ms | "
                        f"p95: {m_res['p95_ms']:.2f}ms | "
                        f"p99: {m_res['p99_ms']:.2f}ms | "
                        f"Peak: {m_res['peak_mb']:.1f}MB | "
                        f"Verified: {m_res['total']:,} OK",
                        flush=True,
                    )

                    # Incremental save
                    results_file.write_text(json.dumps(all_data, indent=2), encoding="utf-8")

                # Summary calculation
                eps_vals = [r["eps"] for r in measured_runs]
                wall_vals = [r["wall_time"] for r in measured_runs]
                p50_vals = [r["p50_ms"] for r in measured_runs]
                p95_vals = [r["p95_ms"] for r in measured_runs]
                p99_vals = [r["p99_ms"] for r in measured_runs]
                peak_vals = [r["peak_mb"] for r in measured_runs]
                cpu_vals = [r["cpu_util_pct"] for r in measured_runs]

                summary = {
                    "output_mode": output_mode,
                    "executor_type": exec_type,
                    "workers": w,
                    "measured_reps": args.reps,
                    "eps_median": statistics.median(eps_vals),
                    "eps_stdev": statistics.stdev(eps_vals) if len(eps_vals) > 1 else 0.0,
                    "eps_runs": eps_vals,
                    "wall_median": statistics.median(wall_vals),
                    "p50_median": statistics.median(p50_vals),
                    "p95_median": statistics.median(p95_vals),
                    "p99_median": statistics.median(p99_vals),
                    "peak_mb_max": max(peak_vals),
                    "cpu_util_median": statistics.median(cpu_vals),
                }
                all_data["summaries"][output_mode][exec_type][str(w)] = summary
                results_file.write_text(json.dumps(all_data, indent=2), encoding="utf-8")

    print("\n" + "=" * 100)
    print("ALL BENCHMARK PASSES COMPLETED SUCCESSFULLY!")
    print("=" * 100)

    # Print Final Consolidated Tables
    for output_mode, bench_title in [("noop", "Benchmark A: Processing-Only (NoOp)"), ("jsonl", "Benchmark B: End-to-End (JSONL Output)")]:
        if output_mode not in all_data["summaries"]:
            continue
        print(f"\n{'='*110}")
        print(f"FINAL TABLE: {bench_title.upper()}")
        print(f"{'='*110}")
        header = (
            f"| {'Executor':<22} | {'Workers':<7} | {'Events':<7} | {'Median EPS':<10} | {'Speedup':<7} | "
            f"{'Efficiency':<10} | {'p50 (ms)':<8} | {'p95 (ms)':<8} | {'p99 (ms)':<8} | {'Peak MB':<8} | {'CPU Util':<8} |"
        )
        sep = f"|{'-'*24}|{'-'*9}|{'-'*9}|{'-'*12}|{'-'*9}|{'-'*12}|{'-'*10}|{'-'*10}|{'-'*10}|{'-'*10}|{'-'*10}|"
        print(header)
        print(sep)

        for exec_type in args.executors:
            exec_label = "ThreadPoolExecutor" if exec_type == "thread" else "ProcessPoolExecutor"
            baseline_eps = all_data["summaries"][output_mode][exec_type]["1"]["eps_median"]
            for w in args.workers:
                s = all_data["summaries"][output_mode][exec_type][str(w)]
                med_eps = s["eps_median"]
                speedup = med_eps / baseline_eps if baseline_eps > 0 else 1.0
                eff = (speedup / w) * 100.0
                row = (
                    f"| {exec_label:<22} | {w:<7} | 100,000 | {med_eps:>10,.0f} | {speedup:>6.2f}x | "
                    f"{eff:>9.1f}% | {s['p50_median']:>8.2f} | {s['p95_median']:>8.2f} | {s['p99_median']:>8.2f} | "
                    f"{s['peak_mb_max']:>8.1f} | {s['cpu_util_median']:>7.1f}% |"
                )
                print(row)
        print(f"{'='*110}\n")


if __name__ == "__main__":
    main()
