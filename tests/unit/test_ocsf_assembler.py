from datetime import datetime, timezone
from ulpf.mapping.mapping_engine import MappingEngine
from ulpf.models.extracted import ExtractedFields
from ulpf.models.ingestion import IngestionMeta
from ulpf.models.ocsf.network_activity import OCSFNetworkActivity
from ulpf.models.raw_event import RawEvent
from ulpf.ocsf.assembler import OCSFAssembler
from pathlib import Path


def test_ocsf_assembler_full_assembly():
    assembler = OCSFAssembler()
    engine = MappingEngine()
    engine.load_directory(Path("config/mappings"))
    profile = engine.get_profile("syslog_generic")
    assert profile is not None

    now = datetime.now(timezone.utc)
    raw = RawEvent(
        raw_event_id="evt-1234",
        payload="<134>Sep 01 12:30:05 fw01 action=deny src=192.168.1.1 dst=8.8.8.8 dpt=53 proto=UDP",
        ingestion=IngestionMeta(
            source_id="test",
            transport="file",
            received_at=now,
            ingestion_sequence=0,
        ),
    )

    extracted = ExtractedFields(
        extension_id="syslog",
        extension_version="1.0.0",
        fields={
            "src": "192.168.1.1",
            "dst": "8.8.8.8",
            "dpt": 53,
            "proto": "UDP",
            "action": "deny",
            "unmapped_key": "val",
        },
        timestamp_raw="Sep 01 12:30:05",
        parse_confidence=1.0,
    )

    ocsf_fields, unmapped = engine.map(extracted, profile)
    event, errors = assembler.assemble(
        raw=raw,
        extracted=extracted,
        profile=profile,
        ocsf_fields=ocsf_fields,
        unmapped=unmapped,
        parse_errors=[],
        start_time=now,
    )

    assert isinstance(event, OCSFNetworkActivity)
    assert errors == []

    # Required OCSF fields
    assert event.class_uid == 4001
    assert event.category_uid == 4
    assert event.activity_id == 3
    assert event.activity_name == "Reset"
    assert event.type_uid == 400103
    assert event.severity_id == 3
    assert event.severity == "Medium"
    assert event.action_id == 2
    assert event.action == "Denied"
    assert event.disposition_id == 2
    assert event.disposition == "Blocked"

    # Endpoints
    assert event.src_endpoint is not None
    assert event.src_endpoint.ip == "192.168.1.1"
    assert event.dst_endpoint is not None
    assert event.dst_endpoint.ip == "8.8.8.8"
    assert event.dst_endpoint.port == 53

    # Connection Info
    assert event.connection_info is not None
    assert event.connection_info.protocol_name == "UDP"

    # Raw log preservation
    assert event.raw_data == raw.payload

    # Unmapped
    assert event.unmapped == {"unmapped_key": "val"}

    # Metadata
    assert event.metadata.uid == "evt-1234"
    assert event.metadata.log_name == "syslog"
    assert event.metadata.product.name == "LogForge"


def test_ocsf_assembler_resilience_on_invalid_fields():
    assembler = OCSFAssembler()
    engine = MappingEngine()
    engine.load_directory(Path("config/mappings"))
    profile = engine.get_profile("generic_passthrough")
    assert profile is not None

    now = datetime.now(timezone.utc)
    raw = RawEvent(
        raw_event_id="evt-bad",
        payload="malformed",
        ingestion=IngestionMeta(
            source_id="test",
            transport="file",
            received_at=now,
            ingestion_sequence=0,
        ),
    )

    extracted = ExtractedFields(
        extension_id="generic",
        extension_version="1.0.0",
        fields={},
        parse_confidence=0.0,
    )

    # Pass something invalid into ocsf_fields that might trigger validation error
    event, errors = assembler.assemble(
        raw=raw,
        extracted=extracted,
        profile=profile,
        ocsf_fields={"activity_id": "not_an_int"},  # Intentionally bad
        unmapped={"raw_payload": "malformed"},
        parse_errors=["Prior error"],
        start_time=now,
    )

    assert isinstance(event, OCSFNetworkActivity)
    assert event.class_uid == 4001
    assert event.raw_data == raw.payload
