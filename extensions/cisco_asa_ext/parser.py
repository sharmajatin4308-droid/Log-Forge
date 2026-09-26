import re
from typing import Any
from ulpf.extension_base import ParserExtension
from ulpf.models.detection import DetectionHints
from ulpf.models.extension import ExtensionMetadata
from ulpf.models.extracted import ExtractedFields
from ulpf.models.raw_event import RawEvent

ASA_HEADER_REGEX = re.compile(
    r"(?:<\d{1,3}>)?(?:([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+)?(?:([^\s:]+)\s+)?%ASA-(\d)-(\d+):\s*(.*)"
)
IPV4_PATTERN = r"(?:\d{1,3}\.){3}\d{1,3}"
IPV6_PATTERN = (
    r"(?:"
    r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|"
    r"(?:[0-9a-fA-F]{1,4}:){1,7}:|"
    r"(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|"
    r"(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}|"
    r"(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}|"
    r"(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}|"
    r"(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}|"
    r"[0-9a-fA-F]{1,4}:(?:(?::[0-9a-fA-F]{1,4}){1,6})|"
    r"::(?:[0-9a-fA-F]{1,4}:)*[0-9a-fA-F]{1,4}|"
    r"::|"
    r"fe80:(?::[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]+|"
    r"::(?:ffff(?::0{1,4})?:)?(?:(?:\d{1,3}\.){3}\d{1,3})|"
    r"(?:[0-9a-fA-F]{1,4}:){1,4}:(?:(?:\d{1,3}\.){3}\d{1,3})"
    r")"
)
IP_PORT_REGEX = re.compile(rf"(?:\b|(?<=[\s(]))({IPV4_PATTERN}|{IPV6_PATTERN})/(\d+)")
PROTO_REGEX = re.compile(r"\b(TCP|UDP|ICMP)\b", re.IGNORECASE)
DIRECTION_REGEX = re.compile(r"\b(Inbound|Outbound)\b", re.IGNORECASE)


class CiscoASAExtension(ParserExtension):
    def __init__(self) -> None:
        self._metadata = ExtensionMetadata(
            extension_id="cisco-asa",
            extension_version="1.0.0",
            format_id="cisco_asa",
            vendor="Cisco",
            product="ASA",
            author="LogForge",
            default_mapping_profile="cisco_asa",
            description="Cisco ASA adaptive security appliance firewall syslog parser",
        )
        self._hints = DetectionHints(
            extension_id="cisco-asa",
            prefixes=[],
            contains=["%ASA-"],
            transports=[],
            priority=10,
        )

    def extension_metadata(self) -> ExtensionMetadata:
        return self._metadata

    def detection_hints(self) -> DetectionHints:
        return self._hints

    def can_process(self, raw: RawEvent) -> bool:
        return "%ASA-" in raw.payload

    def parse(self, raw: RawEvent) -> ExtractedFields:
        match = ASA_HEADER_REGEX.search(raw.payload)
        if not match:
            return ExtractedFields(
                extension_id="cisco-asa",
                extension_version="1.0.0",
                fields={},
                parse_confidence=0.0,
            )

        ts_raw, host, sev, msgid, body = match.groups()

        fields: dict[str, Any] = {
            "asa_severity": sev,
            "asa_msgid": msgid,
        }
        if host:
            fields["host"] = host

        # Extract direction
        dir_match = DIRECTION_REGEX.search(body)
        if dir_match:
            fields["direction"] = dir_match.group(1).capitalize()

        # Extract protocol
        proto_match = PROTO_REGEX.search(body)
        if proto_match:
            fields["proto"] = proto_match.group(1).upper()

        # Extract IP/port pairs
        ip_ports = IP_PORT_REGEX.findall(body)
        if len(ip_ports) >= 2:
            fields["src"] = ip_ports[0][0]
            fields["src_port"] = int(ip_ports[0][1])
            fields["dst"] = ip_ports[1][0]
            fields["dst_port"] = int(ip_ports[1][1])
        elif len(ip_ports) == 1:
            fields["src"] = ip_ports[0][0]
            fields["src_port"] = int(ip_ports[0][1])

        # Extract action
        body_lower = body.lower()
        if any(w in body_lower for w in ("deny", "denied", "drop", "blocked", "block")):
            fields["action"] = "deny"
        elif any(w in body_lower for w in ("built", "allow", "permit", "permitted")):
            fields["action"] = "allow"
        elif "teardown" in body_lower:
            fields["action"] = "teardown"

        return ExtractedFields(
            extension_id="cisco-asa",
            extension_version="1.0.0",
            fields=fields,
            timestamp_raw=ts_raw,
            parse_confidence=1.0,
            mapping_profile_hint="cisco_asa",
        )
