from abc import ABC, abstractmethod
from collections.abc import Iterator
from ..models.raw_event import RawEvent


class IngestionSource(ABC):
    @abstractmethod
    def events(self) -> Iterator[RawEvent]:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @property
    @abstractmethod
    def source_id(self) -> str:
        ...
