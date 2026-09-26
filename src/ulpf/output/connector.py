from typing import Protocol
from ..models.ulpf_record import ULPFRecord


class OutputConnector(Protocol):
    def write(self, record: ULPFRecord) -> None:
        ...

    def flush(self) -> None:
        ...

    def close(self) -> None:
        ...
