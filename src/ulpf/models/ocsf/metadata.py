from pydantic import BaseModel, ConfigDict


class OCSFProduct(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = "LogForge"
    vendor_name: str = "Hacked"
    version: str = "1.0.0"


class OCSFMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: str = "1.4.0"               # OCSF schema version
    product: OCSFProduct = OCSFProduct()
    log_name: str | None = None          # Format family identifier
    original_time: str | None = None     # Raw timestamp string from the log
    uid: str | None = None               # raw_event_id
