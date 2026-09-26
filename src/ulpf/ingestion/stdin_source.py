from collections.abc import Iterator
from datetime import datetime, timezone
import sys
import uuid

from .base import IngestionSource
from ..models.ingestion import IngestionMeta
from ..models.raw_event import RawEvent


class StdinIngestionSource(IngestionSource):
    def __init__(
        self,
        source_id: str = "stdin",
        source_hint: str | None = None,
    ) -> None:
        self._source_id = source_id
        self.source_hint = source_hint

    @property
    def source_id(self) -> str:
        return self._source_id

    def events(self) -> Iterator[RawEvent]:
        sequence = 0
        stdin_stream = getattr(sys.stdin, "buffer", sys.stdin)

        for line in stdin_stream:
            if isinstance(line, bytes):
                decoded = line.decode("utf-8", errors="replace")
                encoding = "utf-8-replace" if "\ufffd" in decoded else "utf-8"
            else:
                decoded = line
                encoding = "utf-8"

            # Strip trailing newline only
            if decoded.endswith("\r\n"):
                decoded = decoded[:-2]
            elif decoded.endswith("\n"):
                decoded = decoded[:-1]

            if not decoded:
                continue

            yield RawEvent(
                raw_event_id=str(uuid.uuid4()),
                payload=decoded,
                payload_encoding=encoding,
                ingestion=IngestionMeta(
                    source_id=self._source_id,
                    transport="stdin",
                    source_hint=self.source_hint,
                    received_at=datetime.now(timezone.utc),
                    ingestion_sequence=sequence,
                ),
            )
            sequence += 1

    def close(self) -> None:
        pass
