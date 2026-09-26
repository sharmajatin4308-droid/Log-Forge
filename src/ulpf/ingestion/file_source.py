from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
import uuid

from .base import IngestionSource
from ..models.ingestion import IngestionMeta
from ..models.raw_event import RawEvent


class FileIngestionSource(IngestionSource):
    def __init__(
        self,
        file_path: Path | str,
        source_id: str | None = None,
        source_hint: str | None = None,
    ) -> None:
        self.file_path = Path(file_path)
        self._source_id = source_id or self.file_path.name
        self.source_hint = source_hint
        self._file = None

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        state["_file"] = None
        return state

    @property
    def source_id(self) -> str:
        return self._source_id

    def events(self) -> Iterator[RawEvent]:
        sequence = 0
        with open(self.file_path, "rb") as f:
            self._file = f
            for line_bytes in f:
                # Check for encoding replacement
                decoded = line_bytes.decode("utf-8", errors="replace")
                encoding = "utf-8"
                if "\ufffd" in decoded:
                    encoding = "utf-8-replace"

                # Strip trailing newline only
                if decoded.endswith("\r\n"):
                    decoded = decoded[:-2]
                elif decoded.endswith("\n"):
                    decoded = decoded[:-1]

                # Skip empty lines silently
                if not decoded:
                    continue

                yield RawEvent(
                    raw_event_id=str(uuid.uuid4()),
                    payload=decoded,
                    payload_encoding=encoding,
                    ingestion=IngestionMeta(
                        source_id=self._source_id,
                        transport="file",
                        source_hint=self.source_hint,
                        received_at=datetime.now(timezone.utc),
                        ingestion_sequence=sequence,
                    ),
                )
                sequence += 1

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()
