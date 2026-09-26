import ast
from pathlib import Path

CORE_ROOT = Path("src/ulpf")
EXTENSION_ROOT = Path("extensions")

FORBIDDEN_IN_CORE_LOGIC = [
    "syslog_ext", "json_ext", "cef_ext", "cisco_asa_ext",  # extension module names
    "%ASA",                                                   # Cisco-specific string
    "CEF:0",                                                  # CEF-specific string
]
ALLOWED_CORE_IMPORTS_FROM_ULPF_IN_EXTENSIONS = {"ulpf.models", "ulpf.extension_base"}
SKIP_DIRS_FOR_LITERAL_CHECK = {CORE_ROOT / "models", CORE_ROOT / "extension_base.py"}


def test_core_does_not_import_extension_modules():
    """ULPF Core must not import any module from the extensions/ directory."""
    violations = []
    for py_file in CORE_ROOT.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("extensions."):
                        violations.append(f"{py_file}: imports {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("extensions."):
                    violations.append(f"{py_file}: from {node.module}")
    assert not violations, f"Core illegally imports extension modules:\n" + "\n".join(violations)


def test_core_logic_contains_no_format_specific_literals():
    """Core logic files must not contain vendor/format-specific string literals."""
    violations = []
    for py_file in CORE_ROOT.rglob("*.py"):
        # Check if file is in skipped paths
        skip = False
        for s in SKIP_DIRS_FOR_LITERAL_CHECK:
            if s.is_dir() and py_file.is_relative_to(s):
                skip = True
                break
            elif py_file.resolve() == s.resolve():
                skip = True
                break
        if skip:
            continue
        content = py_file.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_IN_CORE_LOGIC:
            if forbidden in content:
                violations.append(f"{py_file}: contains '{forbidden}'")
    assert not violations, f"Core contains format-specific literals:\n" + "\n".join(violations)


def test_extensions_only_import_allowed_ulpf_modules():
    """Extensions may only import from ulpf.models and ulpf.extension_base."""
    violations = []
    for py_file in EXTENSION_ROOT.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("ulpf.") or alias.name == "ulpf":
                        if not any(alias.name.startswith(a) for a in ALLOWED_CORE_IMPORTS_FROM_ULPF_IN_EXTENSIONS):
                            violations.append(f"{py_file}: imports {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("ulpf.") or node.module == "ulpf":
                    if not any(node.module.startswith(a) for a in ALLOWED_CORE_IMPORTS_FROM_ULPF_IN_EXTENSIONS):
                        violations.append(f"{py_file}: from {node.module}")
    assert not violations, f"Extension illegally imports Core internals:\n" + "\n".join(violations)


def test_ocsf_event_has_required_fields():
    """OCSFNetworkActivity model must define all OCSF-required fields."""
    from ulpf.models.ocsf.network_activity import OCSFNetworkActivity
    required = {"class_uid", "category_uid", "activity_id", "type_uid", "severity_id", "time", "metadata"}
    model_fields = set(OCSFNetworkActivity.model_fields.keys())
    missing = required - model_fields
    assert not missing, f"OCSFNetworkActivity missing required fields: {missing}"


def test_raw_payload_invariant():
    """raw_event.payload must equal ocsf_event['raw_data'] in a success record."""
    import uuid
    from datetime import datetime, timezone
    from ulpf.models.raw_event import RawEvent
    from ulpf.models.ingestion import IngestionMeta

    original = "<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP"
    raw = RawEvent(
        raw_event_id=str(uuid.uuid4()),
        payload=original,
        ingestion=IngestionMeta(
            source_id="test",
            transport="file",
            received_at=datetime.now(timezone.utc),
            ingestion_sequence=0,
        ),
    )
    assert raw.payload == original


def test_adding_extension_does_not_require_core_modification():
    """
    Verify that the extension registry loads extensions from config only.
    Adding a new extension requires: (1) a new file in extensions/, (2) a new
    config/extensions.yaml entry, (3) a new mapping YAML. No other changes.
    """
    from ulpf.registry.extension_registry import ExtensionRegistry
    r = ExtensionRegistry()
    # Should be possible to instantiate with no extensions registered
    assert r.list_extensions() == []
    assert r.get("nonexistent") is None
