import importlib
import logging
from pathlib import Path
import sys
from typing import Any
import yaml

from ..extension_base import ParserExtension
from ..models.detection import DetectionHints
from ..models.extension import ExtensionMetadata

logger = logging.getLogger(__name__)


class ExtensionRegistry:
    def __init__(self) -> None:
        self._extensions: dict[str, ParserExtension] = {}
        self._metadata: dict[str, ExtensionMetadata] = {}
        self._hints: dict[str, DetectionHints] = {}
        self._sorted_hints: list[tuple[str, DetectionHints]] = []

    def load_from_config(self, config_path: Path) -> None:
        """
        Read config/extensions.yaml.
        For each enabled extension: importlib.import_module(module), getattr(module, class)()
        Register via self.register().
        Resilient to malformed YAML, invalid entries, broken imports, or constructor failures.
        """
        if not config_path.exists():
            return

        # Ensure project root / current working directory is on sys.path
        project_root = config_path.resolve().parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        cwd_str = str(Path.cwd().resolve())
        if cwd_str not in sys.path:
            sys.path.insert(0, cwd_str)

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as e:
            logger.warning(
                "Failed to parse extension configuration file %s: %s",
                config_path,
                e,
            )
            return

        if raw_data is None:
            entries = []
        elif isinstance(raw_data, dict):
            if "extensions" in raw_data:
                if isinstance(raw_data["extensions"], list):
                    entries = raw_data["extensions"]
                else:
                    logger.warning(
                        "Invalid 'extensions' key in %s: expected list, got %s",
                        config_path,
                        type(raw_data["extensions"]).__name__,
                    )
                    return
            else:
                logger.warning(
                    "Missing 'extensions' key in configuration dict in %s",
                    config_path,
                )
                return
        elif isinstance(raw_data, list):
            entries = raw_data
        else:
            logger.warning(
                "Unsupported root structure in %s: expected dict or list, got %s",
                config_path,
                type(raw_data).__name__,
            )
            return

        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                logger.warning(
                    "Skipping invalid extension entry at index %d in %s: expected dict, got %s",
                    idx,
                    config_path,
                    type(entry).__name__,
                )
                continue

            if not entry.get("enabled", True):
                continue

            module_name = entry.get("module")
            class_name = entry.get("class")
            if not module_name or not isinstance(module_name, str) or not module_name.strip():
                logger.warning(
                    "Skipping extension entry at index %d in %s: missing or invalid 'module' key",
                    idx,
                    config_path,
                )
                continue
            if not class_name or not isinstance(class_name, str) or not class_name.strip():
                logger.warning(
                    "Skipping extension entry at index %d (module: '%s') in %s: missing or invalid 'class' key",
                    idx,
                    module_name,
                    config_path,
                )
                continue

            try:
                mod = importlib.import_module(module_name)
            except Exception as e:
                logger.warning(
                    "Skipping extension '%s.%s' (index %d in %s): failed to import module '%s': %s",
                    module_name,
                    class_name,
                    idx,
                    config_path,
                    module_name,
                    e,
                )
                continue

            try:
                cls = getattr(mod, class_name)
            except AttributeError as e:
                logger.warning(
                    "Skipping extension '%s.%s' (index %d in %s): class '%s' not found in module '%s': %s",
                    module_name,
                    class_name,
                    idx,
                    config_path,
                    class_name,
                    module_name,
                    e,
                )
                continue

            try:
                instance = cls()
            except Exception as e:
                logger.warning(
                    "Skipping extension '%s.%s' (index %d in %s): failed to instantiate class: %s",
                    module_name,
                    class_name,
                    idx,
                    config_path,
                    e,
                )
                continue

            self.register(instance)

    def register(self, extension: ParserExtension) -> None:
        """Register a single instance. Raise ValueError on duplicate extension_id."""
        meta = extension.extension_metadata()
        if meta.extension_id in self._extensions:
            raise ValueError(f"Duplicate extension_id: {meta.extension_id}")
        hints = extension.detection_hints()
        self._extensions[meta.extension_id] = extension
        self._metadata[meta.extension_id] = meta
        self._hints[meta.extension_id] = hints
        # Re-sort and cache hints by DetectionHints.priority ASC
        sorted_hints = list(self._hints.items())
        sorted_hints.sort(key=lambda x: x[1].priority)
        self._sorted_hints = sorted_hints

    def get(self, extension_id: str) -> ParserExtension | None:
        return self._extensions.get(extension_id)

    def get_metadata(self, extension_id: str) -> ExtensionMetadata | None:
        """Returns cached metadata for the extension, or None if not found."""
        return self._metadata.get(extension_id)

    def all_hints(self) -> list[tuple[str, DetectionHints]]:
        """Returns [(extension_id, hints)] sorted by DetectionHints.priority ASC from cache."""
        return list(self._sorted_hints)

    def list_extensions(self) -> list[ExtensionMetadata]:
        """Returns metadata for all registered extensions from cache."""
        return list(self._metadata.values())
