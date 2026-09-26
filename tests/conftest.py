from datetime import datetime, timezone
from pathlib import Path
import uuid
import pytest

from ulpf.config.settings import Settings
from ulpf.models.ingestion import IngestionMeta
from ulpf.models.raw_event import RawEvent
from ulpf.pipeline.factory import create_pipeline


@pytest.fixture
def make_raw_event():
    def _make(
        payload: str,
        transport: str = "file",
        source_id: str = "test",
        source_hint: str | None = None,
        source_address: str | None = None,
        sequence: int = 0,
    ) -> RawEvent:
        return RawEvent(
            raw_event_id=str(uuid.uuid4()),
            payload=payload,
            payload_encoding="utf-8",
            ingestion=IngestionMeta(
                source_id=source_id,
                transport=transport,
                source_address=source_address,
                source_hint=source_hint,
                received_at=datetime.now(timezone.utc),
                ingestion_sequence=sequence,
            ),
        )

    return _make


@pytest.fixture
def pipeline_fixture():
    settings = Settings()
    # Use output_mode="stdout" with no source so process_one can be called directly
    return create_pipeline(settings, output_mode="stdout")
