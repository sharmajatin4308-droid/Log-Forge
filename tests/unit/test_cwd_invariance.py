import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from ulpf.config.settings import Settings, find_project_root, is_logforge_root
from ulpf.registry.extension_registry import ExtensionRegistry
from ulpf.api.app import app


def test_is_logforge_root():
    root = find_project_root()
    assert is_logforge_root(root) is True

    with tempfile.TemporaryDirectory() as tmpdir:
        assert is_logforge_root(Path(tmpdir)) is False


def test_find_project_root_env_override(monkeypatch):
    root = find_project_root()
    monkeypatch.setenv("LOGFORGE_PROJECT_ROOT", str(root))
    assert find_project_root() == root

    # Invalid directory raises ValueError
    monkeypatch.setenv("LOGFORGE_PROJECT_ROOT", "/nonexistent/path/for/logforge/root")
    with pytest.raises(ValueError, match="does not exist"):
        find_project_root()

    # Valid directory without LogForge markers raises ValueError
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("LOGFORGE_PROJECT_ROOT", tmpdir)
        with pytest.raises(ValueError, match="not a valid LogForge repository root"):
            find_project_root()


def test_settings_load_from_different_cwds(monkeypatch):
    original_cwd = os.getcwd()
    root = find_project_root()

    try:
        # 1. From project root
        os.chdir(root)
        s1 = Settings.load()
        assert Path(s1.pipeline.extensions_config).is_absolute()
        assert Path(s1.pipeline.extensions_config).exists()
        assert Path(s1.pipeline.mappings_dir).is_absolute()
        assert Path(s1.pipeline.mappings_dir).exists()

        # 2. From src/
        os.chdir(root / "src")
        s2 = Settings.load()
        assert Path(s2.pipeline.extensions_config).is_absolute()
        assert Path(s2.pipeline.extensions_config).exists()

        # 3. From unrelated temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.chdir(tmpdir)
                s3 = Settings.load()
                assert Path(s3.pipeline.extensions_config).is_absolute()
                assert Path(s3.pipeline.extensions_config).exists()

                # Ensure registry loads all 5 standard extensions from tempdir CWD
                registry = ExtensionRegistry()
                registry.load_from_config(Path(s3.pipeline.extensions_config))
                ext_ids = {meta.extension_id for meta in registry.list_extensions()}
                assert {"cisco-asa", "cef", "syslog", "json", "generic"}.issubset(ext_ids)
            finally:
                os.chdir(original_cwd)
    finally:
        os.chdir(original_cwd)


def test_api_extension_loading_across_cwds(monkeypatch):
    """
    Test actual API startup and extension loading via TestClient from multiple CWDs:
    Project Root, src/, and an unrelated temporary directory.
    """
    original_cwd = os.getcwd()
    root = find_project_root()

    targets = [root, root / "src", Path(tempfile.gettempdir())]

    try:
        for target in targets:
            os.chdir(target)
            client = TestClient(app)
            response = client.get("/api/extensions")
            assert response.status_code == 200, f"Failed GET /api/extensions from CWD: {target}"
            data = response.json()
            assert "extensions" in data
            ext_ids = {e["extension_id"] for e in data["extensions"]}
            assert "syslog" in ext_ids, f"syslog missing from {target}"
            assert "generic" in ext_ids, f"generic missing from {target}"
            assert "cisco-asa" in ext_ids, f"cisco-asa missing from {target}"

            # Verify single event ingestion from this CWD
            payload = "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP"
            ingest_resp = client.post("/api/ingest", json={"payload": payload})
            assert ingest_resp.status_code == 200, f"Failed ingestion from {target}"
            rec = ingest_resp.json()
            assert rec["ulpf_metadata"]["extension_id"] == "syslog"
            assert rec["ulpf_metadata"]["parse_status"] == "success"
    finally:
        os.chdir(original_cwd)
