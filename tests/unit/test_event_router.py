from datetime import datetime, timezone
import uuid
from ulpf.extension_base import ParserExtension
from ulpf.models.detection import DetectionHints
from ulpf.models.extension import ExtensionMetadata
from ulpf.models.extracted import ExtractedFields
from ulpf.models.ingestion import IngestionMeta
from ulpf.models.raw_event import RawEvent
from ulpf.registry.extension_registry import ExtensionRegistry
from ulpf.routing.event_router import EventRouter


class MockSyslogExt(ParserExtension):
    def extension_metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            extension_id="syslog",
            extension_version="1.0.0",
            format_id="syslog",
            default_mapping_profile="syslog_generic",
        )

    def detection_hints(self) -> DetectionHints:
        return DetectionHints(
            extension_id="syslog",
            prefixes=["<134>", "<14>"],
            contains=["fw01"],
            priority=50,
        )

    def can_process(self, raw: RawEvent) -> bool:
        return raw.payload.startswith("<")

    def parse(self, raw: RawEvent) -> ExtractedFields:
        return ExtractedFields(extension_id="syslog", extension_version="1.0.0", fields={})


class MockCiscoExt(ParserExtension):
    def extension_metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            extension_id="cisco-asa",
            extension_version="1.0.0",
            format_id="cisco_asa",
            default_mapping_profile="cisco_asa",
        )

    def detection_hints(self) -> DetectionHints:
        return DetectionHints(
            extension_id="cisco-asa",
            contains=["%ASA-"],
            priority=10,  # Higher priority than syslog
        )

    def can_process(self, raw: RawEvent) -> bool:
        return "%ASA-" in raw.payload

    def parse(self, raw: RawEvent) -> ExtractedFields:
        return ExtractedFields(extension_id="cisco-asa", extension_version="1.0.0", fields={})


class MockBrokenExt(ParserExtension):
    def extension_metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            extension_id="broken",
            extension_version="1.0.0",
            format_id="broken",
            default_mapping_profile="generic_passthrough",
        )

    def detection_hints(self) -> DetectionHints:
        return DetectionHints(
            extension_id="broken",
            prefixes=["BROKEN"],
            priority=5,
        )

    def can_process(self, raw: RawEvent) -> bool:
        raise RuntimeError("Explosion inside can_process")

    def parse(self, raw: RawEvent) -> ExtractedFields:
        return ExtractedFields(extension_id="broken", extension_version="1.0.0", fields={})


def _make_raw(payload: str, transport: str = "file", source_hint: str | None = None) -> RawEvent:
    return RawEvent(
        raw_event_id=str(uuid.uuid4()),
        payload=payload,
        ingestion=IngestionMeta(
            source_id="test",
            transport=transport,
            source_hint=source_hint,
            received_at=datetime.now(timezone.utc),
            ingestion_sequence=0,
        ),
    )


def test_event_router_flow():
    registry = ExtensionRegistry()
    registry.register(MockSyslogExt())
    registry.register(MockCiscoExt())
    registry.register(MockBrokenExt())

    router = EventRouter(registry)

    # 1. Cisco ASA event with both Cisco tag and Syslog prefix
    # Cisco has priority=10 and matching contains '%ASA-'
    raw_cisco = _make_raw("<134>Sep 01 12:30:05 %ASA-4-106001: Denied")
    assert router.route(raw_cisco) == "cisco-asa"

    # 2. Pure Syslog event
    raw_syslog = _make_raw("<134>Sep 01 12:30:05 fw01 action=deny")
    assert router.route(raw_syslog) == "syslog"

    # 3. Explicit source_hint override
    raw_override = _make_raw("random payload", source_hint="syslog")
    # syslog can_process checks for starting with '<', so this fails can_process and falls through
    assert router.route(raw_override) == "generic"

    raw_override_valid = _make_raw("<134>payload", source_hint="syslog")
    assert router.route(raw_override_valid) == "syslog"

    # 4. Resilience when can_process raises
    raw_broken = _make_raw("BROKEN message")
    # broken raises exception -> router continues and falls back to generic
    assert router.route(raw_broken) == "generic"

    # 5. Unknown log -> fallback to generic
    raw_unknown = _make_raw("completely unknown arbitrary log line")
    assert router.route(raw_unknown) == "generic"
