import io
from pathlib import Path
import pytest

from ulpf.ingestion.file_source import FileIngestionSource
from ulpf.ingestion.stdin_source import StdinIngestionSource
from ulpf.ingestion.http_source import create_raw_event_from_http


def test_file_ingestion_source(tmp_path: Path):
    test_file = tmp_path / "test.log"
    test_file.write_text("line 1\nline 2\n\nline 3\n", encoding="utf-8")

    source = FileIngestionSource(file_path=test_file, source_hint="syslog")
    events = list(source.events())

    assert len(events) == 3
    assert events[0].payload == "line 1"
    assert events[0].ingestion.ingestion_sequence == 0
    assert events[0].ingestion.source_hint == "syslog"
    assert events[1].payload == "line 2"
    assert events[1].ingestion.ingestion_sequence == 1
    assert events[2].payload == "line 3"
    assert events[2].ingestion.ingestion_sequence == 2


def test_file_ingestion_source_missing():
    source = FileIngestionSource(file_path=Path("non_existent_12345.log"))
    with pytest.raises(FileNotFoundError):
        list(source.events())


def test_stdin_ingestion_source(monkeypatch):
    mock_stdin = io.StringIO("line alpha\nline beta\n")
    monkeypatch.setattr("sys.stdin", mock_stdin)

    source = StdinIngestionSource(source_hint="json")
    events = list(source.events())

    assert len(events) == 2
    assert events[0].payload == "line alpha"
    assert events[0].ingestion.transport == "stdin"
    assert events[0].ingestion.source_hint == "json"
    assert events[1].payload == "line beta"


def test_http_raw_event_creation():
    raw1 = create_raw_event_from_http("http event 1", source_hint="cef", source_address="192.168.1.100")
    assert raw1.payload == "http event 1"
    assert raw1.ingestion.transport == "http"
    assert raw1.ingestion.source_hint == "cef"
    assert raw1.ingestion.source_address == "192.168.1.100"
