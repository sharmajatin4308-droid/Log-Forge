import pytest
from pathlib import Path
from ulpf.extension_base import ParserExtension
from ulpf.models.detection import DetectionHints
from ulpf.models.extension import ExtensionMetadata
from ulpf.models.extracted import ExtractedFields
from ulpf.models.raw_event import RawEvent
from ulpf.registry.extension_registry import ExtensionRegistry


class DummyExtensionA(ParserExtension):
    def extension_metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            extension_id="dummy-a",
            extension_version="1.0.0",
            format_id="dummy",
            default_mapping_profile="generic_passthrough",
        )

    def detection_hints(self) -> DetectionHints:
        return DetectionHints(
            extension_id="dummy-a",
            prefixes=["DUMMY-A"],
            priority=20,
        )

    def can_process(self, raw: RawEvent) -> bool:
        return raw.payload.startswith("DUMMY-A")

    def parse(self, raw: RawEvent) -> ExtractedFields:
        return ExtractedFields(
            extension_id="dummy-a",
            extension_version="1.0.0",
            fields={"msg": raw.payload},
        )


class DummyExtensionB(ParserExtension):
    def extension_metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            extension_id="dummy-b",
            extension_version="1.0.0",
            format_id="dummy",
            default_mapping_profile="generic_passthrough",
        )

    def detection_hints(self) -> DetectionHints:
        return DetectionHints(
            extension_id="dummy-b",
            prefixes=["DUMMY-B"],
            priority=10,  # Higher priority (lower number)
        )

    def can_process(self, raw: RawEvent) -> bool:
        return raw.payload.startswith("DUMMY-B")

    def parse(self, raw: RawEvent) -> ExtractedFields:
        return ExtractedFields(
            extension_id="dummy-b",
            extension_version="1.0.0",
            fields={"msg": raw.payload},
        )


def test_registry_registration_and_hints():
    registry = ExtensionRegistry()
    assert registry.list_extensions() == []
    assert registry.get("dummy-a") is None

    ext_a = DummyExtensionA()
    ext_b = DummyExtensionB()

    registry.register(ext_a)
    registry.register(ext_b)

    assert registry.get("dummy-a") is ext_a
    assert registry.get("dummy-b") is ext_b

    # Duplicate registration raises ValueError
    with pytest.raises(ValueError):
        registry.register(ext_a)

    # Hints sorted by priority ASC (10 before 20)
    hints = registry.all_hints()
    assert len(hints) == 2
    assert hints[0][0] == "dummy-b"
    assert hints[0][1].priority == 10
    assert hints[1][0] == "dummy-a"
    assert hints[1][1].priority == 20

    # List metadata
    meta_list = registry.list_extensions()
    ids = {m.extension_id for m in meta_list}
    assert ids == {"dummy-a", "dummy-b"}


class BrokenConstructorExtension(ParserExtension):
    def __init__(self):
        super().__init__()
        raise RuntimeError("Simulated crash in extension __init__")

    def extension_metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            extension_id="broken-init",
            extension_version="1.0.0",
            format_id="broken",
            default_mapping_profile="generic_passthrough",
        )

    def detection_hints(self) -> DetectionHints:
        return DetectionHints(extension_id="broken-init", prefixes=["BROKEN"])

    def can_process(self, raw: RawEvent) -> bool:
        return False

    def parse(self, raw: RawEvent) -> ExtractedFields:
        return ExtractedFields(
            extension_id="broken-init",
            extension_version="1.0.0",
            fields={},
        )


def test_load_from_config_malformed_yaml(tmp_path: Path, caplog):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("extensions: [unclosed_bracket: ", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    assert registry.list_extensions() == []
    assert "Failed to parse extension configuration file" in caplog.text


def test_load_from_config_missing_module_key(tmp_path: Path, caplog):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("""
extensions:
  - class: DummyExtensionA
    enabled: true
""", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    assert registry.list_extensions() == []
    assert "missing or invalid 'module' key" in caplog.text


def test_load_from_config_missing_class_key(tmp_path: Path, caplog):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("""
extensions:
  - module: tests.unit.test_extension_registry
    enabled: true
""", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    assert registry.list_extensions() == []
    assert "missing or invalid 'class' key" in caplog.text


def test_load_from_config_nonexistent_module(tmp_path: Path, caplog):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("""
extensions:
  - module: nonexistent.fake_module_12345
    class: SomeClass
    enabled: true
""", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    assert registry.list_extensions() == []
    assert "failed to import module 'nonexistent.fake_module_12345'" in caplog.text


def test_load_from_config_nonexistent_class(tmp_path: Path, caplog):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("""
extensions:
  - module: tests.unit.test_extension_registry
    class: NonExistentClassXYZ
    enabled: true
""", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    assert registry.list_extensions() == []
    assert "class 'NonExistentClassXYZ' not found in module 'tests.unit.test_extension_registry'" in caplog.text


def test_load_from_config_constructor_failure(tmp_path: Path, caplog):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("""
extensions:
  - module: tests.unit.test_extension_registry
    class: BrokenConstructorExtension
    enabled: true
""", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    assert registry.list_extensions() == []
    assert "failed to instantiate class" in caplog.text


def test_load_from_config_mixed_valid_and_invalid(tmp_path: Path, caplog):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("""
extensions:
  - module: nonexistent.module
    class: BadClass
    enabled: true
  - module: tests.unit.test_extension_registry
    class: DummyExtensionA
    enabled: true
  - module: tests.unit.test_extension_registry
    class: BrokenConstructorExtension
    enabled: true
  - module: tests.unit.test_extension_registry
    class: DummyExtensionB
    enabled: true
  - class: MissingModuleClass
    enabled: true
""", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    # Valid extensions A and B should be successfully loaded despite 3 invalid entries
    loaded = {m.extension_id for m in registry.list_extensions()}
    assert loaded == {"dummy-a", "dummy-b"}
    assert registry.get("dummy-a") is not None
    assert registry.get("dummy-b") is not None
    # Warnings logged for the bad entries
    assert "nonexistent.module" in caplog.text
    assert "BrokenConstructorExtension" in caplog.text


def test_load_from_config_disabled_entries_skipped(tmp_path: Path):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("""
extensions:
  - module: tests.unit.test_extension_registry
    class: DummyExtensionA
    enabled: false
  - module: tests.unit.test_extension_registry
    class: DummyExtensionB
    enabled: true
""", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    assert registry.get("dummy-a") is None
    assert registry.get("dummy-b") is not None
    assert len(registry.list_extensions()) == 1


def test_load_from_config_unsupported_root_structures(tmp_path: Path, caplog):
    registry = ExtensionRegistry()

    # Case 1: Root is a scalar string
    cfg_scalar = tmp_path / "scalar.yaml"
    cfg_scalar.write_text("just a string scalar", encoding="utf-8")
    registry.load_from_config(cfg_scalar)
    assert registry.list_extensions() == []
    assert "Unsupported root structure" in caplog.text

    # Case 2: Dict without 'extensions' key
    cfg_no_ext = tmp_path / "no_ext.yaml"
    cfg_no_ext.write_text("other_key: 123", encoding="utf-8")
    registry.load_from_config(cfg_no_ext)
    assert registry.list_extensions() == []
    assert "Missing 'extensions' key" in caplog.text

    # Case 3: 'extensions' is not a list
    cfg_ext_not_list = tmp_path / "ext_not_list.yaml"
    cfg_ext_not_list.write_text("extensions: 'not a list'", encoding="utf-8")
    registry.load_from_config(cfg_ext_not_list)
    assert registry.list_extensions() == []
    assert "Invalid 'extensions' key" in caplog.text


def test_load_from_config_warning_content_detail(tmp_path: Path, caplog):
    cfg = tmp_path / "extensions.yaml"
    cfg.write_text("""
extensions:
  - module: some.missing.pkg
    class: MyMissingParser
    enabled: true
""", encoding="utf-8")
    registry = ExtensionRegistry()
    registry.load_from_config(cfg)
    # Check that warning logs identify module and class
    record = next(r for r in caplog.records if r.levelname == "WARNING")
    assert "some.missing.pkg" in record.message
    assert "MyMissingParser" in record.message

