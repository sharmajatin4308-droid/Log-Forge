import re
from typing import Any
from ulpf.extension_base import ParserExtension
from ulpf.models.detection import DetectionHints
from ulpf.models.extension import ExtensionMetadata
from ulpf.models.extracted import ExtractedFields
from ulpf.models.raw_event import RawEvent


def _parse_cef_extension(ext_str: str) -> dict[str, str]:
    """
    Parse CEF extension key=value pairs handling values with spaces.
    Regex matches key= followed by value up to next key= or end of string.
    """
    fields: dict[str, str] = {}
    pattern = re.compile(r'(\w+)=((?:\\=|[^=])*)(?:\s+(?=\w+=)|$)')
    for match in pattern.finditer(ext_str):
        k = match.group(1).strip()
        v = match.group(2).strip()
        # Unescape escaped =, |, or \
        v = v.replace(r"\=", "=").replace(r"\|", "|").replace(r"\\", "\\")
        fields[k] = v
    return fields


class CEFExtension(ParserExtension):
    def __init__(self) -> None:
        self._metadata = ExtensionMetadata(
            extension_id="cef",
            extension_version="1.0.0",
            format_id="cef",
            vendor=None,
            product=None,
            author="LogForge",
            default_mapping_profile="cef_standard",
            description="ArcSight Common Event Format (CEF) parser",
        )
        self._hints = DetectionHints(
            extension_id="cef",
            prefixes=["CEF:"],
            contains=["CEF:0|", "CEF:"],
            transports=[],
            priority=20,
        )

    def extension_metadata(self) -> ExtensionMetadata:
        return self._metadata

    def detection_hints(self) -> DetectionHints:
        return self._hints

    def can_process(self, raw: RawEvent) -> bool:
        return "CEF:" in raw.payload

    def parse(self, raw: RawEvent) -> ExtractedFields:
        idx = raw.payload.find("CEF:")
        if idx == -1:
            return ExtractedFields(
                extension_id="cef",
                extension_version="1.0.0",
                fields={},
                parse_confidence=0.0,
            )

        cef_text = raw.payload[idx:]
        parts = re.split(r"(?<!\\)\|", cef_text)

        if len(parts) < 8:
            return ExtractedFields(
                extension_id="cef",
                extension_version="1.0.0",
                fields={},
                parse_confidence=0.0,
            )

        cef_prefix, dev_vendor, dev_product, dev_version, sig_id, name, severity = parts[:7]
        ext_str = "|".join(parts[7:])

        fields: dict[str, Any] = {
            "DeviceVendor": dev_vendor.replace(r"\|", "|"),
            "DeviceProduct": dev_product.replace(r"\|", "|"),
            "DeviceVersion": dev_version.replace(r"\|", "|"),
            "SignatureID": sig_id.replace(r"\|", "|"),
            "Name": name.replace(r"\|", "|"),
            "Severity": severity.replace(r"\|", "|"),
        }

        kv_fields = _parse_cef_extension(ext_str)
        fields.update(kv_fields)

        timestamp_raw = fields.get("rt")

        return ExtractedFields(
            extension_id="cef",
            extension_version="1.0.0",
            fields=fields,
            timestamp_raw=timestamp_raw,
            parse_confidence=1.0,
            mapping_profile_hint="cef_standard",
        )
