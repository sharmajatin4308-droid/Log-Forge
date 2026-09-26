def test_empty_string_resilience(pipeline_fixture, make_raw_event):
    sample = ""
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)
    assert record.raw_event.payload == ""
    assert record.ocsf_event["raw_data"] == ""
    assert record.ulpf_metadata.parse_status in ("partial", "failed")


def test_truncated_json_resilience(pipeline_fixture, make_raw_event):
    sample = '{"timestamp": "2024-09-01T12:00:00Z", "incomplete":'
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)
    assert record.raw_event.payload == sample
    assert record.ocsf_event["raw_data"] == sample
    assert record.ulpf_metadata.parse_status in ("partial", "failed")


def test_oversized_event_resilience(pipeline_fixture, make_raw_event):
    # Event with 1MB payload
    sample = "<134>Sep 01 12:30:05 fw01 action=deny msg=" + ("A" * 1024 * 1024)
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)
    assert len(record.raw_event.payload) > 1024 * 1024
    assert record.ocsf_event["class_uid"] == 4001
    assert record.ulpf_metadata.extension_id == "syslog"


def test_missing_mapping_profile_fallback(pipeline_fixture, make_raw_event):
    sample = "some random log line"
    raw = make_raw_event(sample, source_hint="generic")
    record = pipeline_fixture.process_one(raw)
    assert record.ulpf_metadata.mapping_profile_id == "generic_passthrough"
    assert record.ocsf_event["class_uid"] == 4001
