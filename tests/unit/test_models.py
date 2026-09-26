from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from ulpf.models.detection import DetectionHints
from ulpf.models.extension import ExtensionMetadata
from ulpf.models.extracted import ExtractedFields
from ulpf.models.ingestion import IngestionMeta
from ulpf.models.pipeline import PipelineStats
from ulpf.models.raw_event import RawEvent
from ulpf.models.ulpf_metadata import ULPFMetadata
from ulpf.models.ulpf_record import ULPFRecord

from ulpf.models.ocsf.metadata import OCSFMetadata, OCSFProduct
from ulpf.models.ocsf.network_activity import OCSFNetworkActivity
from ulpf.models.ocsf.network_connection_info import OCSFNetworkConnectionInfo
from ulpf.models.ocsf.network_endpoint import OCSFNetworkEndpoint


def test_ingestion_meta():
    now = datetime.now(timezone.utc)
    meta = IngestionMeta(
        source_id="src-1",
        transport="file",
        received_at=now,
        ingestion_sequence=0,
    )
    assert meta.source_id == "src-1"
    assert meta.transport == "file"
    assert meta.source_address is None
    assert meta.source_hint is None
    assert meta.received_at == now
    assert meta.ingestion_sequence == 0

    # Test immutability
    with pytest.raises(ValidationError):
        meta.transport = "http"  # type: ignore


def test_raw_event():
    now = datetime.now(timezone.utc)
    raw = RawEvent(
        raw_event_id="uuid-1234",
        payload="test log payload",
        ingestion=IngestionMeta(
            source_id="src-1",
            transport="stdin",
            received_at=now,
            ingestion_sequence=1,
        ),
    )
    assert raw.raw_event_id == "uuid-1234"
    assert raw.payload == "test log payload"
    assert raw.payload_encoding == "utf-8"

    # Test immutability
    with pytest.raises(ValidationError):
        raw.payload = "modified"  # type: ignore


def test_detection_hints():
    hints = DetectionHints(
        extension_id="test-ext",
        prefixes=["<134>"],
        contains=["ASA-"],
        transports=["syslog", "file"],
        priority=10,
    )
    assert hints.extension_id == "test-ext"
    assert hints.prefixes == ["<134>"]
    assert hints.contains == ["ASA-"]
    assert hints.transports == ["syslog", "file"]
    assert hints.priority == 10

    # Default values
    default_hints = DetectionHints(extension_id="default-ext")
    assert default_hints.prefixes == []
    assert default_hints.contains == []
    assert default_hints.transports == []
    assert default_hints.priority == 100

    # Immutability
    with pytest.raises(ValidationError):
        hints.priority = 50  # type: ignore


def test_extension_metadata():
    ext_meta = ExtensionMetadata(
        extension_id="cisco-asa",
        extension_version="1.0.0",
        format_id="cisco_asa",
        vendor="Cisco",
        product="ASA",
        default_mapping_profile="cisco_asa",
    )
    assert ext_meta.extension_id == "cisco-asa"
    assert ext_meta.author == "LogForge"
    assert ext_meta.vendor == "Cisco"
    assert ext_meta.description == ""

    # Immutability
    with pytest.raises(ValidationError):
        ext_meta.version = "2.0.0"  # type: ignore


def test_extracted_fields():
    extracted = ExtractedFields(
        extension_id="cisco-asa",
        extension_version="1.0.0",
        fields={"src": "192.168.1.1", "action": "deny"},
        timestamp_raw="Sep 01 12:30:05",
        parse_confidence=0.95,
        mapping_profile_hint="cisco_asa",
    )
    assert extracted.extension_id == "cisco-asa"
    assert extracted.fields["src"] == "192.168.1.1"
    assert extracted.parse_confidence == 0.95

    # Immutability
    with pytest.raises(ValidationError):
        extracted.parse_confidence = 0.5  # type: ignore


def test_ulpf_metadata():
    now = datetime.now(timezone.utc)
    meta = ULPFMetadata(
        raw_event_id="uuid-1",
        extension_id="syslog",
        extension_version="1.0.0",
        mapping_profile_id="syslog_generic",
        mapping_profile_version="1.0.0",
        parse_status="success",
        processed_at=now,
        processing_duration_ms=0.45,
        transport="file",
    )
    assert meta.parse_status == "success"
    assert meta.parse_errors == []
    assert meta.schema_version == "1.4.0"
    assert meta.source_hint_used is None

    # Invalid parse_status
    with pytest.raises(ValidationError):
        ULPFMetadata(
            raw_event_id="uuid-1",
            extension_id="syslog",
            extension_version="1.0.0",
            mapping_profile_id="syslog_generic",
            mapping_profile_version="1.0.0",
            parse_status="invalid_status",  # type: ignore
            processed_at=now,
            processing_duration_ms=0.45,
            transport="file",
        )


def test_ulpf_record():
    now = datetime.now(timezone.utc)
    raw = RawEvent(
        raw_event_id="uuid-1",
        payload="test payload",
        ingestion=IngestionMeta(
            source_id="test",
            transport="file",
            received_at=now,
            ingestion_sequence=0,
        ),
    )
    meta = ULPFMetadata(
        raw_event_id="uuid-1",
        extension_id="syslog",
        extension_version="1.0.0",
        mapping_profile_id="syslog_generic",
        mapping_profile_version="1.0.0",
        parse_status="success",
        processed_at=now,
        processing_duration_ms=0.5,
        transport="file",
    )
    record = ULPFRecord(
        ocsf_event={"class_uid": 4001, "raw_data": "test payload"},
        ulpf_metadata=meta,
        raw_event=raw,
    )
    assert record.ocsf_event["class_uid"] == 4001
    assert record.ulpf_metadata.raw_event_id == raw.raw_event_id
    assert record.raw_event.payload == "test payload"

    # Serialization roundtrip
    dumped = record.model_dump()
    assert dumped["ocsf_event"]["class_uid"] == 4001
    assert dumped["ulpf_metadata"]["parse_status"] == "success"
    assert dumped["raw_event"]["payload"] == "test payload"


def test_pipeline_stats():
    stats = PipelineStats()
    assert stats.total == 0
    assert stats.eps == 0.0
    assert stats.success_rate == 0.0

    stats.total = 100
    stats.success = 90
    stats.partial = 5
    stats.failed = 5
    stats.total_duration_ms = 500.0  # 0.5 sec

    assert stats.eps == 200.0
    assert stats.success_rate == 0.90


def test_ocsf_models():
    prod = OCSFProduct()
    assert prod.name == "LogForge"
    assert prod.vendor_name == "Hacked"

    meta = OCSFMetadata()
    assert meta.version == "1.4.0"
    assert meta.product.name == "LogForge"

    src_ep = OCSFNetworkEndpoint(ip="10.0.0.1", port=12345)
    dst_ep = OCSFNetworkEndpoint(ip="8.8.8.8", port=53)
    conn = OCSFNetworkConnectionInfo(protocol_name="UDP", protocol_num=17, direction_id=1)

    act = OCSFNetworkActivity(
        time=1693571405000,
        activity_id=1,
        activity_name="Open",
        type_uid=400101,
        severity_id=1,
        src_endpoint=src_ep,
        dst_endpoint=dst_ep,
        connection_info=conn,
        raw_data="raw log line",
    )

    assert act.class_uid == 4001
    assert act.category_uid == 4
    assert act.type_uid == 400101
    assert act.src_endpoint.ip == "10.0.0.1"
    assert act.dst_endpoint.port == 53
    assert act.connection_info.protocol_name == "UDP"
    assert act.raw_data == "raw log line"

    # Immutability
    with pytest.raises(ValidationError):
        act.time = 99999  # type: ignore
