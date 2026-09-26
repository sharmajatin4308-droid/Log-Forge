from typing import Sequence
from .connector import OutputConnector
from ..models.ulpf_record import ULPFRecord


class MultiConnector:
    def __init__(self, connectors: Sequence[OutputConnector]) -> None:
        self.connectors = list(connectors)

    def write(self, record: ULPFRecord) -> None:
        for conn in self.connectors:
            conn.write(record)

    def flush(self) -> None:
        for conn in self.connectors:
            conn.flush()

    def close(self) -> None:
        for conn in self.connectors:
            conn.close()
