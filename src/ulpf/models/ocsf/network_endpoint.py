from pydantic import BaseModel, ConfigDict


class OCSFNetworkEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    ip: str | None = None
    port: int | None = None
    hostname: str | None = None
    mac: str | None = None
    name: str | None = None
