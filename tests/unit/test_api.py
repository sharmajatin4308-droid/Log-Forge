from fastapi.testclient import TestClient
from ulpf.api.app import app

client = TestClient(app)


def test_api_health():
    import time
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert data["ocsf_version"] == "1.4.0"
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0.0

    time.sleep(0.02)
    response2 = client.get("/api/health")
    data2 = response2.json()
    assert data2["uptime_seconds"] >= data["uptime_seconds"]



def test_api_extensions():
    response = client.get("/api/extensions")
    assert response.status_code == 200
    data = response.json()
    assert "extensions" in data
    ext_ids = {e["extension_id"] for e in data["extensions"]}
    assert "syslog" in ext_ids
    assert "cisco-asa" in ext_ids
    assert "cef" in ext_ids
    assert "json" in ext_ids
    assert "generic" in ext_ids


def test_api_ingest_single():
    payload = "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP"
    response = client.post("/api/ingest", json={"payload": payload})
    assert response.status_code == 200
    record = response.json()

    assert "ocsf_event" in record
    assert "ulpf_metadata" in record
    assert "raw_event" in record

    assert record["ocsf_event"]["class_uid"] == 4001
    assert record["ocsf_event"]["raw_data"] == payload
    assert record["ulpf_metadata"]["extension_id"] == "syslog"
    assert record["ulpf_metadata"]["parse_status"] == "success"


def test_api_single_ingest_immediate_visibility():
    # 1. Start clean by clearing events
    del_resp = client.delete("/api/events")
    assert del_resp.status_code == 200

    # 2. Ingest single event A
    payload_a = "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.1 dst=8.8.8.8 dpt=53 proto=UDP"
    resp_a = client.post("/api/ingest", json={"payload": payload_a})
    assert resp_a.status_code == 200
    rec_a = resp_a.json()
    id_a = rec_a["ulpf_metadata"]["raw_event_id"]

    # 3. Immediately query GET /api/events without waiting for buffer timeout
    list_resp = client.get("/api/events")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 1
    assert len(data["records"]) == 1
    assert data["records"][0]["ulpf_metadata"]["raw_event_id"] == id_a

    # 4. Immediately query GET /api/events/{id}
    item_resp = client.get(f"/api/events/{id_a}")
    assert item_resp.status_code == 200
    assert item_resp.json()["raw_event"]["payload"] == payload_a

    # 5. Multiple sequential single-event ingestions
    payload_b = "<134>Sep 01 12:30:06 fw01 action=allow src=10.0.0.2 dst=1.1.1.1 dpt=443 proto=TCP"
    resp_b = client.post("/api/ingest", json={"payload": payload_b})
    assert resp_b.status_code == 200
    id_b = resp_b.json()["ulpf_metadata"]["raw_event_id"]

    list_resp2 = client.get("/api/events")
    assert list_resp2.status_code == 200
    data2 = list_resp2.json()
    assert data2["total"] == 2
    ids_found = {r["ulpf_metadata"]["raw_event_id"] for r in data2["records"]}
    assert id_a in ids_found
    assert id_b in ids_found

    # 6. Failed ingestion does not create an invalid persisted record
    bad_resp = client.post("/api/ingest", json={})
    assert bad_resp.status_code == 422
    list_resp3 = client.get("/api/events")
    assert list_resp3.json()["total"] == 2

    # 7. Clean up
    client.delete("/api/events")



def test_api_ingest_batch():
    events = [
        "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP",
        '{"timestamp": "2024-09-01T12:30:05Z", "src_ip": "10.0.0.4", "destination_ip": "8.8.8.8", "port": 53, "protocol": "UDP", "action": "deny"}',
    ]
    response = client.post("/api/ingest/batch", json={"events": events})
    assert response.status_code == 200
    data = response.json()

    assert "records" in data
    assert len(data["records"]) == 2
    assert "stats" in data
    assert data["stats"]["total"] == 2
    assert data["stats"]["success"] == 2


def test_api_root_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "LogForge" in response.text


def test_api_list_events(tmp_path, monkeypatch):
    from ulpf.api.routes import events as events_module

    # Mock _read_output_file to return sample records
    sample_records = [
        {
            "ulpf_metadata": {"raw_event_id": "ev-1", "parse_status": "success"},
            "raw_event": {"raw_event_id": "ev-1", "payload": "sample 1"},
            "ocsf_event": {"class_uid": 4001, "raw_data": "sample 1"},
        },
        {
            "ulpf_metadata": {"raw_event_id": "ev-2", "parse_status": "partial"},
            "raw_event": {"raw_event_id": "ev-2", "payload": "sample 2"},
            "ocsf_event": {"class_uid": 4001, "raw_data": "sample 2"},
        },
    ]
    monkeypatch.setattr(events_module, "_read_output_file", lambda: list(sample_records))

    # Test list without filter
    res = client.get("/api/events?limit=10&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["records"]) == 2

    # Test filter by status
    res_filtered = client.get("/api/events?status=success")
    assert res_filtered.status_code == 200
    assert res_filtered.json()["total"] == 1

    # Test get by id
    res_single = client.get("/api/events/ev-1")
    assert res_single.status_code == 200
    assert res_single.json()["raw_event"]["raw_event_id"] == "ev-1"

    # Test get by non-existent id
    res_404 = client.get("/api/events/non-existent-999")
    assert res_404.status_code == 404


def test_api_clear_events(tmp_path, monkeypatch):
    import json
    from ulpf.api.routes import events as events_module

    fake_file = tmp_path / "events.jsonl"
    fake_file.write_text('{"id": 1}\n{"id": 2}\n{"id": 3}\n', encoding="utf-8")

    monkeypatch.setattr(events_module, "OUTPUT_FILE", fake_file)

    res = client.delete("/api/events")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "cleared"
    assert data["deleted_count"] == 3

    # File should now be empty
    assert fake_file.read_text(encoding="utf-8") == ""

    # Subsequent delete on empty file
    res2 = client.delete("/api/events")
    assert res2.status_code == 200
    assert res2.json()["deleted_count"] == 0


