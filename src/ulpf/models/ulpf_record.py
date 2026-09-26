from pydantic import BaseModel, ConfigDict
from .raw_event import RawEvent
from .ulpf_metadata import ULPFMetadata


class ULPFRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    ocsf_event: dict
    ulpf_metadata: ULPFMetadata
    raw_event: RawEvent
