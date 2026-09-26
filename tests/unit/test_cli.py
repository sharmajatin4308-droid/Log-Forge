from pathlib import Path
from typer.testing import CliRunner
from ulpf.cli.cli import app

runner = CliRunner()


def test_cli_process_file_stdout():
    sample_file = Path("samples/syslog/sample_001.log")
    result = runner.invoke(
        app,
        ["process", str(sample_file), "--output", "stdout", "--stats"],
    )
    assert result.exit_code == 0
    assert "LogForge Pipeline Execution Summary" in result.output
    assert "Throughput" in result.output


def test_cli_process_nonexistent_file():
    result = runner.invoke(
        app,
        ["process", "non_existent_file_123.log"],
    )
    assert result.exit_code == 2
    assert "does not exist" in result.output


def test_cli_extensions_list():
    result = runner.invoke(app, ["extensions", "list"])
    assert result.exit_code == 0
    assert "Registered LogForge Parser Extensions" in result.output
    assert "syslog" in result.output
    assert "cisco-asa" in result.output
    assert "cef" in result.output
    assert "json" in result.output
    assert "generic" in result.output


def test_cli_extensions_validate():
    sample_file = Path("samples/syslog/sample_001.log")
    result = runner.invoke(
        app,
        ["extensions", "validate", "syslog", str(sample_file)],
    )
    assert result.exit_code == 0
    assert "Event #1" in result.output
    assert "can_process=True" in result.output


def test_cli_extensions_validate_missing():
    sample_file = Path("samples/syslog/sample_001.log")
    result = runner.invoke(
        app,
        ["extensions", "validate", "nonexistent-ext", str(sample_file)],
    )
    assert result.exit_code == 2
    assert "not found" in result.output


def test_cli_validate_jsonl(tmp_path: Path):
    # Process a few events to a temporary jsonl file first
    sample_file = Path("samples/syslog/sample_001.log")
    out_file = tmp_path / "test_out.jsonl"
    proc_res = runner.invoke(
        app,
        ["process", str(sample_file), "--output", "jsonl", "--out-file", str(out_file)],
    )
    assert proc_res.exit_code == 0
    assert out_file.exists()

    val_res = runner.invoke(app, ["validate", str(out_file)])
    assert val_res.exit_code == 0
    assert "Valid OCSF 1.4.0" in val_res.output


def test_cli_validate_missing_file():
    result = runner.invoke(app, ["validate", "missing.jsonl"])
    assert result.exit_code == 2
    assert "not found" in result.output


def test_cli_bench():
    sample_file = Path("samples/syslog/sample_001.log")
    result = runner.invoke(
        app,
        ["bench", str(sample_file), "--events", "10"],
    )
    assert result.exit_code == 0
    assert "LogForge Benchmark Performance Report" in result.output
    assert "Throughput" in result.output
