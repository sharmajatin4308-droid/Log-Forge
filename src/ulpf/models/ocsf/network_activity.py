from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from .network_endpoint import OCSFNetworkEndpoint
from .network_connection_info import OCSFNetworkConnectionInfo
from .metadata import OCSFMetadata


class OCSFNetworkActivity(BaseModel):
    """
    OCSF NetworkActivity class (class_uid=4001).
    Fields verified against schema.ocsf.io/1.4.0/classes/network_activity.
    Only fields actually used in the MVP are included.
    """
    model_config = ConfigDict(frozen=True)

    # Classification (required)
    class_uid: int = 4001
    class_name: str = "Network Activity"
    category_uid: int = 4
    category_name: str = "Network Activity"
    activity_id: int = 0                    # Default: Unknown; set by mapping
    activity_name: str | None = None        # String sibling of activity_id
    type_uid: int = 400100                  # Computed: class_uid * 100 + activity_id
    type_name: str | None = None

    # Occurrence (required)
    time: int = 0                           # Unix epoch milliseconds; required
    severity_id: int = 0                    # Required; 0=Unknown default
    severity: str | None = None

    # Primary (recommended)
    src_endpoint: OCSFNetworkEndpoint | None = None
    dst_endpoint: OCSFNetworkEndpoint | None = None
    connection_info: OCSFNetworkConnectionInfo | None = None
    action_id: int | None = None            # From security_control profile
    action: str | None = None
    disposition_id: int | None = None
    disposition: str | None = None
    message: str | None = None              # Human-readable description

    # Context (optional)
    raw_data: str | None = None             # OFFICIAL OCSF field: original raw log line
    unmapped: dict[str, Any] | None = None  # OFFICIAL OCSF field: unmapped vendor fields
    metadata: OCSFMetadata = Field(default_factory=OCSFMetadata)  # Required
