import io
import json
import sys
import threading

from ..models.ulpf_record import ULPFRecord


class StdoutConnector:
    def __init__(self, pretty: bool = False) -> None:
        self.pretty = pretty
        self._lock = threading.Lock()

    def write(self, record: ULPFRecord) -> None:
        if self.pretty:
            data = record.model_dump()
            output = json.dumps(data, indent=2, default=str) + "\n"
        else:
            output = record.model_dump_json() + "\n"
        with self._lock:
            try:
                sys.stdout.write(output)
            except UnicodeEncodeError:
                # Handle streams that cannot encode specific Unicode (e.g. Windows CP1252 with \ufffd)
                buffer = getattr(sys.stdout, "buffer", None)
                if buffer is not None:
                    try:
                        buffer.write(output.encode("utf-8", errors="replace"))
                        buffer.flush()
                        return
                    except (AttributeError, io.UnsupportedOperation, OSError):
                        pass
                # Fallback for streams without a usable .buffer (e.g. custom text wrappers)
                try:
                    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
                    safe_output = output.encode(encoding, errors="replace").decode(encoding, errors="replace")
                    sys.stdout.write(safe_output)
                except (UnicodeEncodeError, LookupError, TypeError):
                    safe_output = output.encode("ascii", errors="replace").decode("ascii")
                    sys.stdout.write(safe_output)
            sys.stdout.flush()


    def flush(self) -> None:
        with self._lock:
            sys.stdout.flush()

    def close(self) -> None:
        with self._lock:
            sys.stdout.flush()

