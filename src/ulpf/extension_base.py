from abc import ABC, abstractmethod
from .models.detection import DetectionHints
from .models.extension import ExtensionMetadata
from .models.extracted import ExtractedFields
from .models.raw_event import RawEvent


class ParserExtension(ABC):
    """
    All parser extensions MUST subclass this.

    ALLOWED imports from ulpf:
      - src.ulpf.models.*         (read-only data types only)
      - src.ulpf.extension_base   (this file)

    FORBIDDEN imports from ulpf:
      - src.ulpf.ingestion
      - src.ulpf.routing
      - src.ulpf.registry
      - src.ulpf.mapping
      - src.ulpf.ocsf
      - src.ulpf.output
      - src.ulpf.pipeline
      - src.ulpf.cli
      - src.ulpf.api
    """

    @abstractmethod
    def extension_metadata(self) -> ExtensionMetadata:
        """Static metadata. No side effects."""
        ...

    @abstractmethod
    def detection_hints(self) -> DetectionHints:
        """Routing hints. No side effects. Must not parse payload."""
        ...

    @abstractmethod
    def can_process(self, raw: RawEvent) -> bool:
        """
        True if this extension can parse this event.
        Must be fast (< 1ms target). May inspect payload.
        MUST NOT raise — return False on any error.
        """
        ...

    @abstractmethod
    def parse(self, raw: RawEvent) -> ExtractedFields:
        """
        Parse raw.payload. Return vendor-native key-value pairs.
        MUST NOT raise — return ExtractedFields(parse_confidence=0.0, fields={}) on failure.
        MUST NOT modify raw.payload.
        MUST NOT perform OCSF field mapping.
        MUST NOT make network calls.
        MUST NOT write files.
        MUST NOT execute system commands.
        Fields keys MUST be vendor-native names, never OCSF names.
        """
        ...
