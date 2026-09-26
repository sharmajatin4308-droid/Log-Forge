def test_syslog_full_pipeline(pipeline_fixture, make_raw_event):
    sample = "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    # Invariants
    assert record.raw_event.payload == sample
    assert record.ocsf_event["raw_data"] == sample
    assert record.ocsf_event["class_uid"] == 4001
    assert record.ocsf_event["category_uid"] == 4

    # Lineage
    assert record.ulpf_metadata.extension_id == "syslog"
    assert record.ulpf_metadata.mapping_profile_id == "syslog_generic"
    assert record.ulpf_metadata.parse_status in ("success", "partial")
    assert record.ulpf_metadata.raw_event_id == raw.raw_event_id

    # Field extraction
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    conn = record.ocsf_event.get("connection_info", {})

    assert src.get("ip") == "10.0.0.4"
    assert dst.get("ip") == "8.8.8.8"
    assert dst.get("port") == 53
    assert conn.get("protocol_name") == "UDP"
    assert record.ocsf_event.get("action_id") == 2      # Denied
    assert record.ocsf_event.get("disposition_id") == 2  # Blocked

    # ULPF contamination check
    assert "parse_status" not in record.ocsf_event
    assert "extension_id" not in record.ocsf_event
    assert "ulpf" not in record.ocsf_event
