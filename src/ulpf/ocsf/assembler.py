from datetime import datetime
import logging
from typing import Any
from pydantic import ValidationError

from ..mapping.profile import MappingProfile
from ..models.extracted import ExtractedFields
from ..models.ocsf.metadata import OCSFMetadata, OCSFProduct
from ..models.ocsf.network_activity import OCSFNetworkActivity
from ..models.ocsf.network_connection_info import OCSFNetworkConnectionInfo
from ..models.ocsf.network_endpoint import OCSFNetworkEndpoint
from ..models.raw_event import RawEvent

logger = logging.getLogger(__name__)

DEFAULT_OCSF_PRODUCT = OCSFProduct(name="LogForge", vendor_name="Hacked", version="1.0.0")

ACTIVITY_ID_NAMES = {
    0: "Unknown",
    1: "Open",
    2: "Close",
    3: "Reset",
    4: "Fail",
    5: "Refuse",
    6: "Traffic",
    7: "Listen",
    99: "Other",
}

ACTION_ID_NAMES = {
    0: "Unknown",
    1: "Allowed",
    2: "Denied",
    3: "Observed",
    4: "Modified",
    99: "Other",
}

SEVERITY_ID_NAMES = {
    0: "Unknown",
    1: "Informational",
    2: "Low",
    3: "Medium",
    4: "High",
    5: "Critical",
    6: "Fatal",
    99: "Other",
}

DISPOSITION_ID_NAMES = {
    0: "Unknown",
    1: "Allowed",
    2: "Blocked",
    3: "Quarantined",
    4: "Isolated",
    5: "Deleted",
    6: "Dropped",
    7: "Custom Action",
    17: "Logged",
    99: "Other",
}

DIRECTION_ID_NAMES = {
    0: "Unknown",
    1: "Inbound",
    2: "Outbound",
    3: "Lateral",
    99: "Other",
}


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


class OCSFAssembler:
    def assemble(
        self,
        raw: RawEvent,
        extracted: ExtractedFields,
        profile: MappingProfile,
        ocsf_fields: dict[str, Any],
        unmapped: dict[str, Any],
        parse_errors: list[str],
        start_time: datetime,
    ) -> tuple[OCSFNetworkActivity, list[str]]:
        """
        Returns (OCSFNetworkActivity, updated_parse_errors).
        Never raises. On Pydantic ValidationError or conversion error: log warning, return minimal valid event,
        add error to parse_errors.
        """
        updated_errors = list(parse_errors)

        try:
            # 1. Build OCSFMetadata
            metadata = OCSFMetadata(
                version="1.4.0",
                product=DEFAULT_OCSF_PRODUCT,
                log_name=ocsf_fields.get("metadata.log_name") or profile.observer_log_name,
                original_time=ocsf_fields.get("metadata.original_time") or extracted.timestamp_raw,
                uid=raw.raw_event_id,
            )

            # 2. Build src_endpoint
            src_ip = ocsf_fields.get("src_endpoint.ip")
            src_port = ocsf_fields.get("src_endpoint.port")
            src_hostname = ocsf_fields.get("src_endpoint.hostname")
            src_mac = ocsf_fields.get("src_endpoint.mac")
            src_name = ocsf_fields.get("src_endpoint.name")

            src_endpoint = None
            if any(x is not None for x in (src_ip, src_port, src_hostname, src_mac, src_name)):
                src_endpoint = OCSFNetworkEndpoint(
                    ip=src_ip,
                    port=src_port,
                    hostname=src_hostname,
                    mac=src_mac,
                    name=src_name,
                )

            # 3. Build dst_endpoint
            dst_ip = ocsf_fields.get("dst_endpoint.ip")
            dst_port = ocsf_fields.get("dst_endpoint.port")
            dst_hostname = ocsf_fields.get("dst_endpoint.hostname")
            dst_mac = ocsf_fields.get("dst_endpoint.mac")
            dst_name = ocsf_fields.get("dst_endpoint.name")

            dst_endpoint = None
            if any(x is not None for x in (dst_ip, dst_port, dst_hostname, dst_mac, dst_name)):
                dst_endpoint = OCSFNetworkEndpoint(
                    ip=dst_ip,
                    port=dst_port,
                    hostname=dst_hostname,
                    mac=dst_mac,
                    name=dst_name,
                )

            # 4. Build connection_info
            protocol_name = ocsf_fields.get("connection_info.protocol_name")
            if protocol_name and isinstance(protocol_name, str):
                protocol_name = protocol_name.upper()

            protocol_num = ocsf_fields.get("connection_info.protocol_num")
            direction_id = ocsf_fields.get("connection_info.direction_id")
            direction = ocsf_fields.get("connection_info.direction")

            if direction and direction_id is None:
                for did, dname in DIRECTION_ID_NAMES.items():
                    if dname.lower() == str(direction).lower():
                        direction_id = did
                        direction = dname
                        break

            connection_info = None
            if any(x is not None for x in (protocol_name, protocol_num, direction_id, direction)):
                connection_info = OCSFNetworkConnectionInfo(
                    protocol_name=protocol_name,
                    protocol_num=protocol_num,
                    direction_id=direction_id,
                    direction=direction,
                )

            # 5. Set activity_id and type_uid
            val = ocsf_fields.get("activity_id", 0)
            activity_id = _safe_int(val, 0)
            type_uid = 4001 * 100 + activity_id
            activity_name = ACTIVITY_ID_NAMES.get(activity_id, "Other")

            # 6. Action, severity, disposition
            action_id = ocsf_fields.get("action_id")
            action = ACTION_ID_NAMES.get(action_id) if action_id is not None else None

            severity_id = _safe_int(ocsf_fields.get("severity_id", 0), 0)
            severity = SEVERITY_ID_NAMES.get(severity_id, "Unknown")

            disposition_id = ocsf_fields.get("disposition_id")
            disposition = DISPOSITION_ID_NAMES.get(disposition_id) if disposition_id is not None else None

            message = ocsf_fields.get("message")
            raw_time = ocsf_fields.get("time", 0)
            event_time = _safe_int(raw_time, 0)

            # 7. unmapped
            clean_unmapped = unmapped if unmapped else None

            event = OCSFNetworkActivity(
                class_uid=4001,
                class_name="Network Activity",
                category_uid=4,
                category_name="Network Activity",
                activity_id=activity_id,
                activity_name=activity_name,
                type_uid=type_uid,
                time=event_time,
                severity_id=severity_id,
                severity=severity,
                src_endpoint=src_endpoint,
                dst_endpoint=dst_endpoint,
                connection_info=connection_info,
                action_id=action_id,
                action=action,
                disposition_id=disposition_id,
                disposition=disposition,
                message=message,
                raw_data=raw.payload,
                unmapped=clean_unmapped,
                metadata=metadata,
            )

            return event, updated_errors

        except Exception as e:
            logger.warning("OCSF assembly error: %s", e)
            updated_errors.append(f"OCSF assembly error: {e}")
            fallback_metadata = OCSFMetadata(
                version="1.4.0",
                product=OCSFProduct(name="LogForge", vendor_name="Hacked", version="1.0.0"),
                uid=raw.raw_event_id,
            )
            fallback_event = OCSFNetworkActivity(
                class_uid=4001,
                class_name="Network Activity",
                category_uid=4,
                category_name="Network Activity",
                activity_id=0,
                type_uid=400100,
                time=0,
                severity_id=0,
                raw_data=raw.payload,
                unmapped=unmapped if unmapped else None,
                metadata=fallback_metadata,
            )
            return fallback_event, updated_errors
