def test_cisco_asa_full_pipeline(pipeline_fixture, make_raw_event):
    sample = "<134>Sep 01 12:30:05 fw01 %ASA-4-106001: Inbound TCP connection denied from 10.0.0.4/54321 to 8.8.8.8/53 flags SYN on interface outside"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    # Invariants
    assert record.raw_event.payload == sample
    assert record.ocsf_event["raw_data"] == sample
    assert record.ocsf_event["class_uid"] == 4001
    assert record.ocsf_event["category_uid"] == 4

    # Lineage
    assert record.ulpf_metadata.extension_id == "cisco-asa"
    assert record.ulpf_metadata.mapping_profile_id == "cisco_asa"
    assert record.ulpf_metadata.parse_status in ("success", "partial")
    assert record.ulpf_metadata.raw_event_id == raw.raw_event_id

    # Field extraction
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    assert src.get("ip") == "10.0.0.4"
    assert src.get("port") == 54321
    assert dst.get("ip") == "8.8.8.8"
    assert dst.get("port") == 53
    assert record.ocsf_event.get("action_id") == 2      # Denied
    assert record.ocsf_event.get("disposition_id") == 2  # Blocked

    # ULPF-specific fields must NOT appear inside ocsf_event
    assert "parse_status" not in record.ocsf_event
    assert "extension_id" not in record.ocsf_event
    assert "ulpf" not in record.ocsf_event


def test_cisco_asa_ipv6_deny(pipeline_fixture, make_raw_event):
    sample = "<134>Sep 01 12:30:05 fw01 %ASA-4-106001: Inbound TCP connection denied from 2001:db8::1/54321 to 2001:db8::2/53 flags SYN on interface outside"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    assert record.ulpf_metadata.parse_status == "success"
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    assert src.get("ip") == "2001:db8::1"
    assert src.get("port") == 54321
    assert dst.get("ip") == "2001:db8::2"
    assert dst.get("port") == 53
    assert record.ocsf_event.get("action_id") == 2


def test_cisco_asa_ipv6_built_with_interface(pipeline_fixture, make_raw_event):
    sample = "<134>Sep 01 12:31:10 fw01 %ASA-6-302013: Built inbound TCP connection 123456 for outside:2001:db8:85a3::8a2e:370:7334/12345 to inside:2001:db8::1/80"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    assert record.ulpf_metadata.parse_status == "success"
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    assert src.get("ip") == "2001:db8:85a3::8a2e:370:7334"
    assert src.get("port") == 12345
    assert dst.get("ip") == "2001:db8::1"
    assert dst.get("port") == 80
    assert record.ocsf_event.get("action_id") == 1


def test_cisco_asa_mixed_ipv4_ipv6(pipeline_fixture, make_raw_event):
    sample = "<134>Sep 01 12:32:45 fw01 %ASA-6-302013: Built outbound TCP connection 987654 for inside:10.0.0.1/51234 to outside:2001:db8::1/443"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    assert record.ulpf_metadata.parse_status == "success"
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    assert src.get("ip") == "10.0.0.1"
    assert src.get("port") == 51234
    assert dst.get("ip") == "2001:db8::1"
    assert dst.get("port") == 443


def test_cisco_asa_mixed_ipv6_ipv4(pipeline_fixture, make_raw_event):
    sample = "<134>Sep 01 12:33:00 fw01 %ASA-6-302013: Built inbound TCP connection 112233 for outside:2001:db8::1/61234 to inside:10.0.0.5/8080"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    assert record.ulpf_metadata.parse_status == "success"
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    assert src.get("ip") == "2001:db8::1"
    assert src.get("port") == 61234
    assert dst.get("ip") == "10.0.0.5"
    assert dst.get("port") == 8080


def test_cisco_asa_ipv6_teardown_and_full_hextet(pipeline_fixture, make_raw_event):
    sample = "<134>Sep 01 12:34:00 fw01 %ASA-6-302014: Teardown TCP connection 123456 for outside:2001:db8:1:2:3:4:5:6/443 to inside:fe80::21b:77ff:fbd4:2c10/51234 duration 0:00:30 bytes 1234 TCP FINs"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    assert record.ulpf_metadata.parse_status == "success"
    src = record.ocsf_event.get("src_endpoint", {})
    dst = record.ocsf_event.get("dst_endpoint", {})
    assert src.get("ip") == "2001:db8:1:2:3:4:5:6"
    assert src.get("port") == 443
    assert dst.get("ip") == "fe80::21b:77ff:fbd4:2c10"
    assert dst.get("port") == 51234

