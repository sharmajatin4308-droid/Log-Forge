import json
from typing import Any
from ulpf.extension_base import ParserExtension
from ulpf.models.detection import DetectionHints
from ulpf.models.extension import ExtensionMetadata
from ulpf.models.extracted import ExtractedFields
from ulpf.models.raw_event import RawEvent


def _flatten_dict(d: dict[str, Any], prefix: str = "", depth: int = 1) -> dict[str, Any]:
    items: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict) and depth < 2:
            items.update(_flatten_dict(v, key, depth + 1))
        else:
            items[key] = v
    return items


class JSONExtension(ParserExtension):
    def __init__(self) -> None:
        self._metadata = ExtensionMetadata(
            extension_id="json",
            extension_version="1.0.0",
            format_id="json",
            vendor=None,
            product=None,
            author="LogForge",
            default_mapping_profile="json_generic",
            description="Structured JSON log parser with nested flattening",
        )
        self._hints = DetectionHints(
            extension_id="json",
            prefixes=["{", "["],
            contains=[],
            transports=[],
            priority=50,
        )

    def extension_metadata(self) -> ExtensionMetadata:
        return self._metadata

    def detection_hints(self) -> DetectionHints:
        return self._hints

    def can_process(self, raw: RawEvent) -> bool:
        payload = raw.payload.strip()
        if not (payload.startswith("{") or payload.startswith("[")):
            return False
        try:
            json.loads(payload)
            return True
        except Exception:
            return False

    def parse(self, raw: RawEvent) -> ExtractedFields:
        try:
            data = json.loads(raw.payload)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]

            if not isinstance(data, dict):
                data = {"value": data}

            timestamp_raw = (
                data.get("timestamp")
                or data.get("@timestamp")
                or data.get("time")
                or data.get("datetime")
            )
            if timestamp_raw is not None:
                timestamp_raw = str(timestamp_raw)

            flattened = _flatten_dict(data)

            return ExtractedFields(
                extension_id="json",
                extension_version="1.0.0",
                fields=flattened,
                timestamp_raw=timestamp_raw,
                parse_confidence=1.0,
                mapping_profile_hint="json_generic",
            )
        except Exception:
            return ExtractedFields(
                extension_id="json",
                extension_version="1.0.0",
                fields={},
                timestamp_raw=None,
                parse_confidence=0.0,
            )
