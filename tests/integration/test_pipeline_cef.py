def test_cef_full_pipeline(pipeline_fixture, make_raw_event):
    sample = "CEF:0|Cisco|ASA|9.8.1|106001|Deny inbound TCP|5|src=10.0.0.4 spt=54321 dst=8.8.8.8 dpt=53 proto=TCP act=deny"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    # Invariants
    assert record.raw_event.payload == sample
    assert record.ocsf_event["raw_data"] == sample
    assert record.ocsf_event["class_uid"] == 4001
    assert record.ocsf_event["category_uid"] == 4

    # Lineage
    assert record.ulpf_metadata.extension_id == "cef"
    assert record.ulpf_metadata.mapping_profile_id == "cef_standard"
    assert record.ulpf_metadata.parse_status in ("success", "partial")
    assert record.ulpf_metadata.raw_event_id == raw.raw_event_id

    # Field extraction
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    conn = record.ocsf_event.get("connection_info", {})

    assert src.get("ip") == "10.0.0.4"
    assert src.get("port") == 54321
    assert dst.get("ip") == "8.8.8.8"
    assert dst.get("port") == 53
    assert conn.get("protocol_name") == "TCP"
    assert record.ocsf_event.get("action_id") == 2      # Denied
    assert record.ocsf_event.get("disposition_id") == 2  # Blocked

    # Contamination check
    assert "parse_status" not in record.ocsf_event
    assert "extension_id" not in record.ocsf_event
    assert "ulpf" not in record.ocsf_event


def test_cef_escaped_pipes(pipeline_fixture, make_raw_event):
    sample = (
        r"CEF:0|Security\|Ops|Firewall\|Plus|2.0|101|Deny \| Inbound Traffic|6|"
        r"src=192.168.1.50 spt=44123 dst=10.0.0.1 dpt=80 proto=TCP act=deny "
        r"msg=Blocked \| Hostile IP detected"
    )
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    assert record.ulpf_metadata.parse_status == "success"
    assert record.ulpf_metadata.extension_id == "cef"

    # Verify extension unescaped pipe in mapped message
    assert record.ocsf_event.get("message") == "Blocked | Hostile IP detected"

    # Verify header unescaped pipe in unmapped vendor/product
    unmapped = record.ocsf_event.get("unmapped", {})
    assert unmapped.get("DeviceVendor") == "Security|Ops"
    assert unmapped.get("DeviceProduct") == "Firewall|Plus"
    assert unmapped.get("SignatureID") == "101"

    # Verify endpoints still extracted accurately
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    assert src.get("ip") == "192.168.1.50"
    assert src.get("port") == 44123
    assert dst.get("ip") == "10.0.0.1"
    assert dst.get("port") == 80


def test_cef_header_escaped_pipe_without_msg(pipeline_fixture, make_raw_event):
    sample = (
        r"CEF:0|Security\|Ops|Firewall\|Plus|2.0|101|Deny \| Inbound Traffic|6|"
        r"src=192.168.1.50 spt=44123 dst=10.0.0.1 dpt=80 proto=TCP act=deny"
    )
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    assert record.ulpf_metadata.parse_status == "success"
    assert record.ocsf_event.get("message") == "Deny | Inbound Traffic"


