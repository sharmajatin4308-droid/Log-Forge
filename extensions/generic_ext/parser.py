from typing import Any
from ulpf.extension_base import ParserExtension
from ulpf.models.detection import DetectionHints
from ulpf.models.extension import ExtensionMetadata
from ulpf.models.extracted import ExtractedFields
from ulpf.models.raw_event import RawEvent


class GenericExtension(ParserExtension):
    def __init__(self) -> None:
        self._metadata = ExtensionMetadata(
            extension_id="generic",
            extension_version="1.0.0",
            format_id="unknown",
            vendor=None,
            product=None,
            author="LogForge",
            default_mapping_profile="generic_passthrough",
            description="Fallback generic parser for unrecognised formats",
        )
        self._hints = DetectionHints(
            extension_id="generic",
            prefixes=[],
            contains=[],
            transports=[],
            priority=999,
        )

    def extension_metadata(self) -> ExtensionMetadata:
        return self._metadata

    def detection_hints(self) -> DetectionHints:
        return self._hints

    def can_process(self, raw: RawEvent) -> bool:
        return True

    def parse(self, raw: RawEvent) -> ExtractedFields:
        fields: dict[str, Any] = {}
        tokens = raw.payload.split()
        for token in tokens:
            if "=" in token:
                k, v = token.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k:
                    fields[k] = v

        return ExtractedFields(
            extension_id="generic",
            extension_version="1.0.0",
            fields=fields,
            timestamp_raw=None,
            parse_confidence=0.3,
            mapping_profile_hint="generic_passthrough",
        )
