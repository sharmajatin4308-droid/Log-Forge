import json
import os
from pathlib import Path
import sys
import time
from typing import Optional

from rich.console import Console
from rich.table import Table
import typer

from ..config.settings import Settings
from ..ingestion.file_source import FileIngestionSource
from ..ingestion.stdin_source import StdinIngestionSource
from ..models.ocsf.network_activity import OCSFNetworkActivity
from ..models.raw_event import RawEvent
from ..models.ingestion import IngestionMeta
from ..pipeline.factory import create_pipeline
from ..pipeline.pipeline import get_recommended_workers
from ..registry.extension_registry import ExtensionRegistry

app = typer.Typer(
    name="logforge",
    help="LogForge — Universal Security Log Pre-processing & Normalization Framework",
    no_args_is_help=True,
)
extensions_app = typer.Typer(help="Manage and validate parser extensions")
app.add_typer(extensions_app, name="extensions")

console = Console()


@app.command(name="process")
def process_cmd(
    file: Optional[Path] = typer.Argument(
        None, help="Input log file (reads stdin if omitted or '-')"
    ),
    source_hint: Optional[str] = typer.Option(
        None, "--source-hint", help="Force extension_id (source_hint override)"
    ),
    output: str = typer.Option(
        "jsonl", "--output", help="Output mode (jsonl | stdout | both)"
    ),
    out_file: Optional[Path] = typer.Option(
        None, "--out-file", help="Output JSONL file (default: output/events.jsonl)"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", help="Config directory (default: ./config)"
    ),
    stats: bool = typer.Option(
        False, "--stats", help="Print pipeline stats on completion"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w",
        help="Parallel worker count (1=sequential, 0=auto-detect CPU count)"
    ),
    executor: Optional[str] = typer.Option(
        None, "--executor",
        help="Executor type: 'process' or 'thread' (default: from config, 'process')"
    ),
    batch_size: int = typer.Option(
        100, "--batch-size", "-b",
        help="Batch size for batched multiprocessing (default: 100)"
    ),
) -> None:
    """
    Process security logs through the ULPF pipeline into OCSF 1.4.0 format.
    """
    try:
        settings = Settings.load(config)
        source = None
        if file is None or str(file) == "-":
            source = StdinIngestionSource(source_hint=source_hint)
        else:
            if not file.exists():
                console.print(f"[bold red]Error:[/bold red] Input file '{file}' does not exist.")
                raise typer.Exit(code=2)
            source = FileIngestionSource(file_path=file, source_hint=source_hint)

        pipeline = create_pipeline(
            settings=settings,
            source=source,
            output_path=out_file,
            source_hint=source_hint,
            output_mode=output,
        )

        effective_workers = workers if workers != 1 else settings.pipeline.workers
        effective_executor = executor if executor is not None else settings.pipeline.executor_type
        effective_batch_size = batch_size if batch_size != 100 else settings.pipeline.batch_size

        if effective_workers == 0:
            effective_workers = get_recommended_workers(effective_executor)

        if effective_workers > 1:
            pipeline_stats = pipeline.run_parallel(
                max_workers=effective_workers,
                executor_type=effective_executor,
                batch_size=effective_batch_size,
            )
        else:
            pipeline_stats = pipeline.run()


        if stats:
            table = Table(title="LogForge Pipeline Execution Summary", border_style="cyan")
            table.add_column("Metric", style="bold")
            table.add_column("Value", style="green")

            table.add_row("Total Events Processed", str(pipeline_stats.total))
            table.add_row("Success", str(pipeline_stats.success))
            table.add_row("Partial (Fallback/Low Conf)", str(pipeline_stats.partial))
            table.add_row("Failed", str(pipeline_stats.failed))
            if 0 < pipeline_stats.total_duration_ms < 0.01:
                duration_str = f"{pipeline_stats.total_duration_ms:.3f} ms"
            else:
                duration_str = f"{pipeline_stats.total_duration_ms:.2f} ms"
            table.add_row("Total Duration", duration_str)
            table.add_row("Throughput (EPS)", f"{pipeline_stats.eps:.2f} events/sec")
            table.add_row(
                "Success Rate", f"{(pipeline_stats.success_rate * 100):.1f}%"
            )
            console.print(table)

        if pipeline_stats.failed > 0:
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Pipeline Error:[/bold red] {e}")
        raise typer.Exit(code=2)


@app.command(name="validate")
def validate_cmd(
    file: Path = typer.Argument(..., help="Path to JSONL file to validate against OCSF schema")
) -> None:
    """
    Validate OCSF events in a JSONL file against OCSFNetworkActivity Pydantic schema.
    """
    if not file.exists():
        console.print(f"[bold red]Error:[/bold red] File '{file}' not found.")
        raise typer.Exit(code=2)

    total = 0
    valid = 0
    invalid = 0

    with open(file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                data = json.loads(line)
                ocsf_payload = data.get("ocsf_event", data)
                OCSFNetworkActivity.model_validate(ocsf_payload)
                valid += 1
            except Exception as e:
                invalid += 1
                console.print(f"[red]Line {line_num} Invalid:[/red] {e}")

    table = Table(title=f"OCSF Validation Results for {file.name}")
    table.add_column("Total Events Checked", justify="right")
    table.add_column("Valid OCSF 1.4.0", justify="right", style="green")
    table.add_column("Invalid", justify="right", style="red" if invalid > 0 else "green")
    table.add_row(str(total), str(valid), str(invalid))
    console.print(table)

    if invalid > 0:
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@app.command(name="bench")
def bench_cmd(
    file: Path = typer.Argument(..., help="Log file to benchmark"),
    events: Optional[int] = typer.Option(
        None, "--events", help="Max events to process (default: all)"
    ),
    source_hint: Optional[str] = typer.Option(
        None, "--source-hint", help="Force extension_id"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", help="Config directory (default: ./config)"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Parallel worker count (1=sequential, 0=auto-detect CPU count)"
    ),
    executor: str = typer.Option(
        "thread", "--executor", help="Executor type: 'thread' or 'process'"
    ),
    batch_size: int = typer.Option(
        100, "--batch-size", "-b", help="Batch size for batched multiprocessing (default: 100)"
    ),
) -> None:
    """
    Benchmark ULPF pipeline throughput and latency percentiles.
    """
    if not file.exists():
        console.print(f"[bold red]Error:[/bold red] File '{file}' not found.")
        raise typer.Exit(code=2)

    settings = Settings.load(config)
    source = FileIngestionSource(file_path=file, source_hint=source_hint)
    # Use DevNull / memory output so benchmark measures pipeline speed without disk bottleneck
    class NoOpConnector:
        def write(self, record): pass
        def flush(self): pass
        def close(self): pass

    pipeline = create_pipeline(
        settings=settings,
        source=source,
        output_mode="stdout",
    )
    pipeline.connector = NoOpConnector()

    effective_workers = workers if workers != 1 else settings.pipeline.workers
    effective_executor = executor if executor != "thread" else settings.pipeline.executor_type
    effective_batch_size = batch_size if batch_size != 100 else settings.pipeline.batch_size
    if effective_workers == 0:
        effective_workers = get_recommended_workers(effective_executor)

    if effective_workers > 1:
        console.print(
            f"[cyan]Starting benchmark on {file.name} (workers={effective_workers}, executor={effective_executor}, batch_size={effective_batch_size})...[/cyan]"
        )
        bench_start = time.monotonic()
        stats = pipeline.run_parallel(
            max_workers=effective_workers,
            executor_type=effective_executor,
            batch_size=effective_batch_size,
        )
        total_time_sec = time.monotonic() - bench_start
        total = stats.total
        success = stats.success
        partial = stats.partial
        failed = stats.failed
        eps = total / total_time_sec if total_time_sec > 0 else 0.0

        table = Table(title="LogForge Benchmark Performance Report", border_style="magenta")
        table.add_column("Benchmark Metric", style="bold")
        table.add_column("Measurement", style="green")

        table.add_row("Events Processed", f"{total:,}")
        table.add_row("Workers", str(effective_workers))
        table.add_row("Executor", effective_executor)
        table.add_row("Total Wall Time", f"{total_time_sec:.3f} s")
        table.add_row("Throughput", f"[bold green]{eps:,.0f} events/sec[/bold green]")
        table.add_row("Success Rate", f"{(success / total * 100):.1f}%" if total else "0%")
        table.add_row("Status Breakdown", f"Success: {success} | Partial: {partial} | Failed: {failed}")
        console.print(table)
        return

    latencies_ms: list[float] = []
    total = 0
    success = 0
    partial = 0
    failed = 0

    console.print(f"[cyan]Starting benchmark on {file.name}...[/cyan]")
    bench_start = time.monotonic()


    for raw in source.events():
        if events is not None and total >= events:
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

    total_time_sec = time.monotonic() - bench_start
    eps = total / total_time_sec if total_time_sec > 0 else 0.0

    latencies_ms.sort()
    p50 = latencies_ms[int(len(latencies_ms) * 0.50)] if latencies_ms else 0.0
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)] if latencies_ms else 0.0

    table = Table(title="LogForge Benchmark Performance Report", border_style="magenta")
    table.add_column("Benchmark Metric", style="bold")
    table.add_column("Measurement", style="green")

    table.add_row("Events Processed", f"{total:,}")
    table.add_row("Total Wall Time", f"{total_time_sec:.3f} s")
    table.add_row("Throughput", f"[bold green]{eps:,.0f} events/sec[/bold green]")
    table.add_row("Latency (P50)", f"{p50:.3f} ms")
    table.add_row("Latency (P95)", f"{p95:.3f} ms")
    table.add_row("Latency (P99)", f"{p99:.3f} ms")
    table.add_row("Success Rate", f"{(success / total * 100):.1f}%" if total else "0%")
    table.add_row("Status Breakdown", f"Success: {success} | Partial: {partial} | Failed: {failed}")

    console.print(table)


@extensions_app.command(name="list")
def extensions_list_cmd(
    config: Optional[Path] = typer.Option(
        None, "--config", help="Config directory (default: ./config)"
    ),
) -> None:
    """
    List all registered extensions: id, version, format, vendor, status.
    """
    settings = Settings.load(config)
    registry = ExtensionRegistry()
    ext_yaml = Path(settings.pipeline.extensions_config)
    if ext_yaml.exists():
        registry.load_from_config(ext_yaml)

    table = Table(title="Registered LogForge Parser Extensions", border_style="blue")
    table.add_column("Extension ID", style="bold cyan")
    table.add_column("Version")
    table.add_column("Format Family")
    table.add_column("Vendor")
    table.add_column("Product")
    table.add_column("Default Mapping")

    for meta in registry.list_extensions():
        table.add_row(
            meta.extension_id,
            meta.extension_version,
            meta.format_id,
            meta.vendor or "-",
            meta.product or "-",
            meta.default_mapping_profile,
        )

    console.print(table)


@extensions_app.command(name="validate")
def extensions_validate_cmd(
    extension_id: str = typer.Argument(..., help="Extension ID to test"),
    file: Path = typer.Argument(..., help="Sample log file to parse"),
    config: Optional[Path] = typer.Option(
        None, "--config", help="Config directory (default: ./config)"
    ),
) -> None:
    """
    Runs one extension against a sample file and displays extracted vendor fields.
    """
    if not file.exists():
        console.print(f"[bold red]Error:[/bold red] File '{file}' not found.")
        raise typer.Exit(code=2)

    settings = Settings.load(config)
    registry = ExtensionRegistry()
    ext_yaml = Path(settings.pipeline.extensions_config)
    if ext_yaml.exists():
        registry.load_from_config(ext_yaml)

    ext = registry.get(extension_id)
    if ext is None:
        console.print(f"[bold red]Error:[/bold red] Extension '{extension_id}' not found.")
        raise typer.Exit(code=2)

    source = FileIngestionSource(file_path=file)
    for idx, raw in enumerate(source.events(), 1):
        can_proc = ext.can_process(raw)
        extracted = ext.parse(raw)
        console.print(
            f"[bold]Event #{idx}[/bold] (can_process={can_proc}, confidence={extracted.parse_confidence}):"
        )
        console.print(extracted.fields)
        if idx >= 5:
            console.print("[dim]... (truncated preview after 5 events)[/dim]")
            break


@app.command(name="serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="API host"),
    port: int = typer.Option(8000, "--port", help="API port"),
) -> None:
    """
    Starts the FastAPI web server.
    """
    import uvicorn
    from ..api.app import app as api_app

    console.print(f"[green]Starting LogForge API server on http://{host}:{port}...[/green]")
    uvicorn.run(api_app, host=host, port=port)
