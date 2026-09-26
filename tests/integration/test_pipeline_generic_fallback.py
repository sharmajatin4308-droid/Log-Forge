def test_generic_fallback_pipeline(pipeline_fixture, make_raw_event):
    sample = "CustomApp 2024-09-01 custom_k1=val1 custom_k2=val2 something_went_wrong"
    raw = make_raw_event(sample, transport="file")
    record = pipeline_fixture.process_one(raw)

    # Invariants
    assert record.raw_event.payload == sample
    assert record.ocsf_event["raw_data"] == sample
    assert record.ocsf_event["class_uid"] == 4001
    assert record.ocsf_event["category_uid"] == 4

    # Lineage
    assert record.ulpf_metadata.extension_id == "generic"
    assert record.ulpf_metadata.mapping_profile_id == "generic_passthrough"
    assert record.ulpf_metadata.parse_status == "partial"  # Confidence 0.3 < 0.5
    assert record.ulpf_metadata.raw_event_id == raw.raw_event_id

    # Unmapped fields check
    unmapped = record.ocsf_event.get("unmapped", {})
    assert unmapped.get("custom_k1") == "val1"
    assert unmapped.get("custom_k2") == "val2"
