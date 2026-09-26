import logging
from pathlib import Path
import threading
import time
from typing import TextIO

from ..models.ulpf_record import ULPFRecord

logger = logging.getLogger(__name__)


class JSONLConnector:
    def __init__(
        self,
        output_path: Path,
        flush_interval_records: int = 100,
        flush_interval_seconds: float = 5.0,
        max_file_size_mb: int = 100,
    ) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.flush_interval_records = flush_interval_records
        self.flush_interval_seconds = flush_interval_seconds
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

        self._lock = threading.Lock()
        self._file: TextIO | None = None
        self._unflushed_count = 0
        self._last_flush_time = time.monotonic()
        self._current_file_size = 0
        self._open_file()

    def _open_file(self) -> None:
        if self._file is not None and not self._file.closed:
            self._file.close()
        self._file = open(self.output_path, "a", encoding="utf-8")
        try:
            self._current_file_size = self.output_path.stat().st_size
        except OSError:
            self._current_file_size = 0

    def _rotate_if_needed_unlocked(self) -> None:
        if self._current_file_size >= self.max_file_size_bytes:
            self._flush_unlocked()
            if self._file and not self._file.closed:
                self._file.close()
            timestamp = int(time.time())
            rotated_name = self.output_path.with_name(
                f"{self.output_path.stem}_{timestamp}{self.output_path.suffix}"
            )
            counter = 1
            while rotated_name.exists():
                rotated_name = self.output_path.with_name(
                    f"{self.output_path.stem}_{timestamp}_{counter}{self.output_path.suffix}"
                )
                counter += 1
            self.output_path.rename(rotated_name)
            self._open_file()

    def write(self, record: ULPFRecord) -> None:
        line = record.model_dump_json() + "\n"
        encoded_len = len(line.encode("utf-8"))
        with self._lock:
            try:
                if self._file is None or self._file.closed:
                    self._open_file()
                self._file.write(line)
                self._current_file_size += encoded_len
            except Exception as e:
                logger.warning("Error writing record, retrying: %s", e)
                try:
                    self._open_file()
                    self._file.write(line)
                    self._current_file_size += encoded_len
                except Exception as e2:
                    logger.error("Failed to write record on retry: %s", e2)
                    return

            self._unflushed_count += 1
            if self._unflushed_count >= self.flush_interval_records:
                self._flush_unlocked()
            elif (time.monotonic() - self._last_flush_time) >= self.flush_interval_seconds:
                self._flush_unlocked()

            if self._current_file_size >= self.max_file_size_bytes:
                self._rotate_if_needed_unlocked()

    def _flush_unlocked(self) -> None:
        if self._file and not self._file.closed:
            self._file.flush()
        self._unflushed_count = 0
        self._last_flush_time = time.monotonic()

    def flush(self) -> None:
        with self._lock:
            self._flush_unlocked()

    def close(self) -> None:
        with self._lock:
            self._flush_unlocked()
            if self._file and not self._file.closed:
                self._file.close()
                self._file = None

