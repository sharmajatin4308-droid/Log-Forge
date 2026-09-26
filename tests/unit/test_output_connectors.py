import io
from pathlib import Path
from datetime import datetime, timezone
from ulpf.models.ingestion import IngestionMeta
from ulpf.models.raw_event import RawEvent
from ulpf.models.ulpf_metadata import ULPFMetadata
from ulpf.models.ulpf_record import ULPFRecord
from ulpf.output.jsonl_connector import JSONLConnector
from ulpf.output.stdout_connector import StdoutConnector
from ulpf.output.multi_connector import MultiConnector


def _make_dummy_record(payload: str = "foo"):
    return ULPFRecord(
        ocsf_event={"class_uid": 4001, "category_uid": 4, "raw_data": payload},
        ulpf_metadata=ULPFMetadata(
            extension_id="test",
            extension_version="1.0",
            mapping_profile_id="test_prof",
            mapping_profile_version="1.0",
            parse_status="success",
            processed_at=datetime.now(timezone.utc),
            processing_duration_ms=1.0,
            transport="file",
            raw_event_id="raw-1",
        ),
        raw_event=RawEvent(
            raw_event_id="raw-1",
            payload=payload,
            ingestion=IngestionMeta(
                source_id="test",
                transport="file",
                received_at=datetime.now(timezone.utc),
                ingestion_sequence=0,
            ),
        ),
    )


def test_jsonl_connector(tmp_path: Path):
    out_file = tmp_path / "sub" / "test.jsonl"
    connector = JSONLConnector(
        output_path=out_file,
        flush_interval_records=2,
        flush_interval_seconds=10.0,
        max_file_size_mb=1,
    )
    rec = _make_dummy_record()

    connector.write(rec)
    connector.write(rec)
    connector.flush()
    connector.close()

    assert out_file.exists()
    lines = out_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2


def test_jsonl_connector_rotation(tmp_path: Path):
    out_file = tmp_path / "rotate_test.jsonl"
    # Set max file size small to trigger rotation
    connector = JSONLConnector(
        output_path=out_file,
        flush_interval_records=1,
        flush_interval_seconds=0.1,
        max_file_size_mb=0,  # 0 MB means size >= 0 bytes triggers rotation
    )
    rec = _make_dummy_record()
    connector.write(rec)
    connector.write(rec)
    connector.close()


def test_stdout_connector(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    conn = StdoutConnector(pretty=False)
    rec = _make_dummy_record()
    conn.write(rec)
    conn.flush()
    conn.close()

    output = buf.getvalue()
    assert "class_uid" in output

    buf_pretty = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf_pretty)
    conn_pretty = StdoutConnector(pretty=True)
    conn_pretty.write(rec)
    assert "\n  " in buf_pretty.getvalue()


def test_multi_connector(tmp_path: Path):
    out1 = tmp_path / "out1.jsonl"
    out2 = tmp_path / "out2.jsonl"
    c1 = JSONLConnector(out1)
    c2 = JSONLConnector(out2)

    multi = MultiConnector([c1, c2])
    rec = _make_dummy_record()
    multi.write(rec)
    multi.flush()
    multi.close()

    assert out1.exists()
    assert out2.exists()


class CP1252StreamWithoutBuffer:
    def __init__(self):
        self.encoding = "cp1252"
        self.buffer = None
        self.written = []

    def write(self, s: str):
        # Strict CP1252 validation - will raise UnicodeEncodeError if chars cannot be encoded
        s.encode("cp1252")
        self.written.append(s)
        return len(s)

    def flush(self):
        pass

    def getvalue(self):
        return "".join(self.written)


class StreamWithBrokenBuffer:
    class BrokenBuffer:
        def write(self, b):
            raise io.UnsupportedOperation("Simulated broken buffer write")

        def flush(self):
            pass

    def __init__(self):
        self.encoding = "cp1252"
        self.buffer = self.BrokenBuffer()
        self.written = []

    def write(self, s: str):
        s.encode("cp1252")
        self.written.append(s)
        return len(s)

    def flush(self):
        pass

    def getvalue(self):
        return "".join(self.written)


def test_stdout_connector_cp1252_without_buffer(monkeypatch):
    stream = CP1252StreamWithoutBuffer()
    monkeypatch.setattr("sys.stdout", stream)

    conn = StdoutConnector(pretty=False)
    # Payload with Unicode replacement char and non-ASCII Unicode outside cp1252
    rec = _make_dummy_record(payload="Corrupted \ufffd symbol \u2713 check")

    conn.write(rec)
    conn.flush()
    conn.close()

    output = stream.getvalue()
    assert output, "Stream should have received output"
    # Ensure replacement characters were used safely without crashing
    assert "Corrupted ? symbol ? check" in output or "Corrupted" in output
    assert "class_uid" in output
    # Exactly one record line written
    assert len(output.strip().split("\n")) == 1


def test_stdout_connector_cp1252_with_usable_buffer(monkeypatch):
    raw_buffer = io.BytesIO()
    stream = io.TextIOWrapper(raw_buffer, encoding="cp1252")
    monkeypatch.setattr("sys.stdout", stream)

    conn = StdoutConnector(pretty=False)
    rec = _make_dummy_record(payload="Corrupted \ufffd and emoji \U0001F600")

    conn.write(rec)
    conn.flush()
    conn.close()

    raw_bytes = raw_buffer.getvalue()
    assert raw_bytes, "Buffer should have received written bytes"
    decoded_utf8 = raw_bytes.decode("utf-8", errors="replace")
    assert "\ufffd" in decoded_utf8
    assert "class_uid" in decoded_utf8
    assert len(decoded_utf8.strip().split("\n")) == 1


def test_stdout_connector_utf8_stream(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    conn = StdoutConnector(pretty=False)
    rec = _make_dummy_record(payload="UTF-8 test: \ufffd, café, \u2713, 🚀")

    conn.write(rec)
    conn.flush()
    conn.close()

    output = buf.getvalue()
    assert "\ufffd" in output
    assert "café" in output
    assert "\u2713" in output
    assert "🚀" in output


def test_stdout_connector_broken_buffer_fallback(monkeypatch):
    stream = StreamWithBrokenBuffer()
    monkeypatch.setattr("sys.stdout", stream)

    conn = StdoutConnector(pretty=False)
    rec = _make_dummy_record(payload="Test fallback with \ufffd char")

    conn.write(rec)
    conn.flush()
    conn.close()

    output = stream.getvalue()
    assert output
    assert "Test fallback with ? char" in output or "Test fallback with" in output
    assert len(output.strip().split("\n")) == 1


def test_stdout_connector_no_duplicate_output_on_fallback(monkeypatch):
    stream = CP1252StreamWithoutBuffer()
    monkeypatch.setattr("sys.stdout", stream)

    conn = StdoutConnector(pretty=False)
    rec1 = _make_dummy_record(payload="Record 1 \ufffd")
    rec2 = _make_dummy_record(payload="Record 2 \ufffd")

    conn.write(rec1)
    conn.write(rec2)
    conn.flush()
    conn.close()

    lines = stream.getvalue().strip().split("\n")
    assert len(lines) == 2, f"Expected exactly 2 lines, got {len(lines)}"


def test_jsonl_connector_utf8_unaffected(tmp_path: Path):
    out_file = tmp_path / "utf8_test.jsonl"
    connector = JSONLConnector(output_path=out_file)
    rec = _make_dummy_record(payload="Unicode payload: \ufffd \u2713 🚀 café")

    connector.write(rec)
    connector.flush()
    connector.close()

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "\ufffd" in content
    assert "\u2713" in content
    assert "🚀" in content
    assert "café" in content

