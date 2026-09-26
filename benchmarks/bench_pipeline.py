import argparse
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
    FIRST_COMPLETED,
)
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc

# Add project root and src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ulpf.config.settings import Settings
from ulpf.ingestion.file_source import FileIngestionSource
from ulpf.pipeline.factory import create_pipeline


class NoOpConnector:
    def write(self, record): pass
    def flush(self): pass
    def close(self): pass


def run_single_benchmark(
    file_path: Path,
    workers: int = 1,
    executor_type: str = "thread",
    max_events: int | None = None,
) -> dict:
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    settings = Settings.load()
    source = FileIngestionSource(file_path=file_path)
    pipeline = create_pipeline(settings, source=source, output_mode="stdout")
    pipeline.connector = NoOpConnector()

    tracemalloc.start()
    latencies_ms: list[float] = []
    total = 0
    success = 0
    partial = 0
    failed = 0

    bench_start = time.monotonic()
    cpu_start = time.process_time()

    if workers <= 1:
        for raw in source.events():
            if max_events is not None and total >= max_events:
                break
            t0 = time.perf_counter()
            rec = pipeline.process_one(raw)
            lat = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(lat)

            total += 1
            st = rec.ulpf_metadata.parse_status
            if st == "success":
                success += 1
            elif st == "partial":
                partial += 1
            else:
                failed += 1
    else:
        if executor_type == "process":
            pipeline.connector = None
            executor_cls = ProcessPoolExecutor
        else:
            executor_cls = ThreadPoolExecutor

        max_in_flight = workers * 4
        futures: dict = {}

        with executor_cls(max_workers=workers) as ex:
            source_iter = iter(source.events())
            source_exhausted = False

            while not source_exhausted or futures:
                while not source_exhausted and len(futures) < max_in_flight:
                    try:
                        raw = next(source_iter)
                        if max_events is not None and (total + len(futures)) >= max_events:
                            source_exhausted = True
                            break
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
                    total += 1
                    st = rec.ulpf_metadata.parse_status
                    if st == "success":
                        success += 1
                    elif st == "partial":
                        partial += 1
                    else:
                        failed += 1

    wall_time = time.monotonic() - bench_start
    cpu_time = time.process_time() - cpu_start
    _current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    eps = total / wall_time if wall_time > 0 else 0.0
    latencies_ms.sort()
    p50 = latencies_ms[int(len(latencies_ms) * 0.50)] if latencies_ms else 0.0
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)] if latencies_ms else 0.0
    peak_mb = peak_mem / (1024 * 1024)
    cpu_util = cpu_time / wall_time if wall_time > 0 else 0.0

    return {
        "workers": workers,
        "executor_type": executor_type,
        "total": total,
        "wall_time": wall_time,
        "cpu_time": cpu_time,
        "cpu_util": cpu_util,
        "eps": eps,
        "p50": p50,
        "p95": p95,
        "p99": p99,
        "peak_mb": peak_mb,
        "success": success,
        "partial": partial,
        "failed": failed,
    }


def print_single_report(res: dict, file_path: Path) -> None:
    env_str = f"Python {platform.python_version()}, {platform.system()} {platform.release()}, {os.environ.get('PROCESSOR_IDENTIFIER', platform.processor())}"
    print("\nLogForge Benchmark Report")
    print("-" * 50)
    print(f"Environment: {env_str}")
    print(f"Input:       {file_path}")
    print(f"Events:      {res['total']:,}")
    print(f"Workers:     {res['workers']} ({res['executor_type']})")
    print("")
    print(f"Throughput:   {res['eps']:,.0f} events/sec")
    print(f"Total time:   {res['wall_time']:.3f} sec")
    print(f"CPU Util:     {res['cpu_util'] * 100:.1f}%")
    print(f"p50 latency:  {res['p50']:.2f} ms")
    print(f"p95 latency:  {res['p95']:.2f} ms")
    print(f"p99 latency:  {res['p99']:.2f} ms")
    print("")
    total = res["total"]
    if total:
        print(f"Parse success:  {res['success']:>6,} / {total:,}  ({(res['success']/total*100):.2f}%)")
        print(f"Parse partial:  {res['partial']:>6,} / {total:,}  ({(res['partial']/total*100):.2f}%)")
        print(f"Parse failed:   {res['failed']:>6,} / {total:,}  ({(res['failed']/total*100):.2f}%)")
    print("")
    print(f"Memory peak: {res['peak_mb']:.1f} MB\n")


def run_comparison_matrix(
    file_path: Path,
    warmup_runs: int = 2,
    repetitions: int = 5,
    worker_counts: list[int] | None = None,
    max_events: int | None = None,
) -> None:
    if worker_counts is None:
        worker_counts = [1, 2, 4, 8]

    executors = ["thread", "process"]
    cpu_id = os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or "Unknown CPU")
    env_str = f"Python {platform.python_version()}, {platform.system()} {platform.release()}, {cpu_id} ({os.cpu_count()} cores)"

    print("=" * 80)
    print("LogForge Parallel Benchmark Matrix")
    print("=" * 80)
    print(f"Environment: {env_str}")
    print(f"Dataset:     {file_path} (max_events={max_events or 'all'})")
    print(f"Repetitions: {repetitions} measured ({warmup_runs} warm-up discarded)")
    print("")

    # Collect baseline (1 worker)
    results = {}

    for exec_type in executors:
        results[exec_type] = {}
        for w in worker_counts:
            print(f"[{exec_type.upper()}] Benchmarking workers={w} (warmup={warmup_runs}, reps={repetitions})...", flush=True)
            # Warm-up runs
            for _ in range(warmup_runs):
                run_single_benchmark(file_path, workers=w, executor_type=exec_type, max_events=max_events)

            # Measured runs
            run_data = []
            for _ in range(repetitions):
                m = run_single_benchmark(file_path, workers=w, executor_type=exec_type, max_events=max_events)
                run_data.append(m)

            # Aggregate
            eps_list = [r["eps"] for r in run_data]
            p50_list = [r["p50"] for r in run_data]
            p95_list = [r["p95"] for r in run_data]
            p99_list = [r["p99"] for r in run_data]
            peak_mb_list = [r["peak_mb"] for r in run_data]
            cpu_util_list = [r["cpu_util"] for r in run_data]

            results[exec_type][w] = {
                "eps_med": statistics.median(eps_list),
                "eps_stdev": statistics.stdev(eps_list) if len(eps_list) > 1 else 0.0,
                "p50_med": statistics.median(p50_list),
                "p95_med": statistics.median(p95_list),
                "p99_med": statistics.median(p99_list),
                "peak_mb_max": max(peak_mb_list),
                "cpu_util_med": statistics.median(cpu_util_list),
            }

    # Print Report
    for exec_type in executors:
        exec_name = "ThreadPoolExecutor" if exec_type == "thread" else "ProcessPoolExecutor"
        print(f"\nExecutor: {exec_name}")
        header = (
            f"┌─────────┬──────────┬─────────┬───────────┬──────────┬──────────┬──────────┬────────────┬──────────┐\n"
            f"│ Workers │ EPS (med)│ Speedup │ Eff.      │ p50 (ms) │ p95 (ms) │ p99 (ms) │ Peak MB    │ CPU Util │\n"
            f"├─────────┼──────────┼─────────┼───────────┼──────────┼──────────┼──────────┼────────────┼──────────┤"
        )
        print(header)
        baseline_eps = results[exec_type][1]["eps_med"]
        for w in worker_counts:
            data = results[exec_type][w]
            med_eps = data["eps_med"]
            speedup = med_eps / baseline_eps if baseline_eps > 0 else 1.0
            efficiency = (speedup / w) * 100.0
            p50 = data["p50_med"]
            p95 = data["p95_med"]
            p99 = data["p99_med"]
            peak_mb = data["peak_mb_max"]
            cpu_pct = data["cpu_util_med"] * 100.0

            row = (
                f"│ {w:>7} │ {med_eps:>8.0f} │ {speedup:>6.2f}x │ {efficiency:>8.1f}% │ "
                f"{p50:>8.2f} │ {p95:>8.2f} │ {p99:>8.2f} │ {peak_mb:>10.1f} │ {cpu_pct:>7.1f}% │"
            )
            print(row)
        footer = f"└─────────┴──────────┴─────────┴───────────┴──────────┴──────────┴──────────┴────────────┴──────────┘"
        print(footer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LogForge Pipeline Benchmark")
    parser.add_argument("--file", type=Path, default=Path("samples/syslog/large.log"))
    parser.add_argument("--events", type=int, default=None)
    parser.add_argument("--workers", "-w", type=int, default=1)
    parser.add_argument("--executor", type=str, default="thread", choices=["thread", "process"])
    parser.add_argument("--compare", action="store_true", help="Run comparison matrix (1/2/4/8 workers x thread/process)")
    parser.add_argument("--warmup", type=int, default=2, help="Number of warmup runs for compare mode")
    parser.add_argument("--reps", type=int, default=5, help="Number of repetitions for compare mode")

    args = parser.parse_args()

    if args.compare:
        run_comparison_matrix(
            file_path=args.file,
            warmup_runs=args.warmup,
            repetitions=args.reps,
            max_events=args.events,
        )
    else:
        res = run_single_benchmark(
            file_path=args.file,
            workers=args.workers,
            executor_type=args.executor,
            max_events=args.events,
        )
        print_single_report(res, args.file)
