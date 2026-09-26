from pydantic import BaseModel, ConfigDict


class OCSFNetworkConnectionInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    protocol_name: str | None = None    # "TCP", "UDP", "ICMP" (uppercase)
    protocol_num: int | None = None     # 6, 17, 1
    direction_id: int | None = None     # 0=Unknown, 1=Inbound, 2=Outbound, 3=Lateral, 99=Other
    direction: str | None = None        # String sibling
    boundary_id: int | None = None
    boundary: str | None = None
