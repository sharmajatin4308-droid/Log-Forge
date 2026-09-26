import re
from typing import Any
from ulpf.extension_base import ParserExtension
from ulpf.models.detection import DetectionHints
from ulpf.models.extension import ExtensionMetadata
from ulpf.models.extracted import ExtractedFields
from ulpf.models.raw_event import RawEvent

SYSLOG_PRI_REGEX = re.compile(r"^<(\d{1,3})>(.*)$")
BSD_HEADER_REGEX = re.compile(
    r"^([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+([^\s:]+)(?::\s*|\s+)(.*)$"
)
RFC5424_HEADER_REGEX = re.compile(
    r"^1\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(?:-\s*)?(.*)$"
)
KV_REGEX = re.compile(r'(?:^|[\s,;])([a-zA-Z0-9_\.\-]+)=(?:"([^"]*)"|\'([^\']*)\'|([^\s,;]+))')


class SyslogExtension(ParserExtension):
    def __init__(self) -> None:
        self._metadata = ExtensionMetadata(
            extension_id="syslog",
            extension_version="1.0.0",
            format_id="syslog",
            vendor=None,
            product=None,
            author="LogForge",
            default_mapping_profile="syslog_generic",
            description="RFC 3164 (BSD) and RFC 5424 syslog parser",
        )
        self._hints = DetectionHints(
            extension_id="syslog",
            prefixes=["<"],
            contains=[],
            transports=[],
            priority=50,
        )

    def extension_metadata(self) -> ExtensionMetadata:
        return self._metadata

    def detection_hints(self) -> DetectionHints:
        return self._hints

    def can_process(self, raw: RawEvent) -> bool:
        return bool(SYSLOG_PRI_REGEX.match(raw.payload))

    def parse(self, raw: RawEvent) -> ExtractedFields:
        pri_match = SYSLOG_PRI_REGEX.match(raw.payload)
        if not pri_match:
            return ExtractedFields(
                extension_id="syslog",
                extension_version="1.0.0",
                fields={},
                timestamp_raw=None,
                parse_confidence=0.0,
            )

        pri_str, remainder = pri_match.groups()
        fields: dict[str, Any] = {"pri": int(pri_str)}
        timestamp_raw: str | None = None
        remainder = remainder.strip()

        # Try RFC5424
        rfc5424_match = RFC5424_HEADER_REGEX.match(remainder)
        if rfc5424_match:
            ts, host, app, pid, msgid, msg_body = rfc5424_match.groups()
            timestamp_raw = ts if ts != "-" else None
            if host != "-":
                fields["hostname"] = host
            if app != "-":
                fields["app"] = app
            if pid != "-":
                fields["pid"] = pid
            if msgid != "-":
                fields["msgid"] = msgid
            body = msg_body
        else:
            # Try BSD
            bsd_match = BSD_HEADER_REGEX.match(remainder)
            if bsd_match:
                ts, host, msg_body = bsd_match.groups()
                timestamp_raw = ts
                fields["hostname"] = host
                body = msg_body
            else:
                body = remainder

        # Parse key=value pairs from body
        kv_pairs = KV_REGEX.findall(body)
        if kv_pairs:
            for k, v1, v2, v3 in kv_pairs:
                val = v1 or v2 or v3
                fields[k] = val
        else:
            fields["msg"] = body

        if "msg" not in fields and body:
            fields["msg"] = body

        return ExtractedFields(
            extension_id="syslog",
            extension_version="1.0.0",
            fields=fields,
            timestamp_raw=timestamp_raw,
            parse_confidence=1.0,
            mapping_profile_hint=None,
        )
