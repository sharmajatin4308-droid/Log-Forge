from pathlib import Path
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from ulpf.models.pipeline import PipelineStats
from ulpf.config.settings import Settings, find_project_root
from ulpf.pipeline.factory import create_pipeline
from ulpf.ingestion.file_source import FileIngestionSource
from ulpf.api.app import app
from ulpf.cli.cli import app as cli_app


def test_pipeline_stats_mathematical_consistency():
    # Normal case
    stats = PipelineStats(total=100, success=95, partial=5, failed=0, total_duration_ms=10.0)
    expected_eps = 100 / (10.0 / 1000.0)  # 10,000 EPS
    assert stats.eps == expected_eps
    assert stats.success_rate == 0.95

    # Zero events guard
    stats_zero_events = PipelineStats(total=0, total_duration_ms=5.0)
    assert stats_zero_events.eps == 0.0
    assert stats_zero_events.success_rate == 0.0

    # Zero or negative duration guard
    stats_zero_duration = PipelineStats(total=100, total_duration_ms=0.0)
    assert stats_zero_duration.eps == 0.0

    stats_neg_duration = PipelineStats(total=100, total_duration_ms=-1.0)
    assert stats_neg_duration.eps == 0.0


def test_pipeline_run_nanosecond_timing():
    root = find_project_root()
    sample_file = root / "samples" / "cisco_asa" / "sample_001.log"
    assert sample_file.exists()

    settings = Settings.load()
    source = FileIngestionSource(sample_file)
    pipeline = create_pipeline(settings=settings, source=source, output_mode="stdout")

    stats = pipeline.run()
    assert stats.total == 21
    assert stats.success == 21
    # On Windows or Linux, perf_counter_ns gives sub-millisecond precision
    assert stats.total_duration_ms > 0.0
    assert stats.eps > 0.0
    assert abs(stats.eps - (stats.total / (stats.total_duration_ms / 1000.0))) < 1e-6


def test_api_batch_ingest_timing():
    client = TestClient(app)
    events = [
        "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP",
        '{"timestamp": "2024-09-01T12:30:05Z", "src_ip": "10.0.0.4", "destination_ip": "8.8.8.8", "port": 53, "protocol": "UDP", "action": "deny"}',
    ]
    response = client.post("/api/ingest/batch", json={"events": events})
    assert response.status_code == 200
    data = response.json()
    stats = data["stats"]
    assert stats["total"] == 2
    assert stats["success"] == 2
    assert stats["total_duration_ms"] > 0.0


def test_cli_stats_formatting():
    root = find_project_root()
    sample_path = str(root / "samples" / "cisco_asa" / "sample_001.log")
    runner = CliRunner()
    result = runner.invoke(cli_app, ["process", sample_path, "--stats"])
    assert result.exit_code == 0
    assert "Total Duration" in result.output
    assert "Throughput (EPS)" in result.output
    # Must NOT report 0.00 ms or 0.00 events/sec
    assert "0.00 ms" not in result.output
    assert "0.00 events/sec" not in result.output

