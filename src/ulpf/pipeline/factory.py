from pathlib import Path
from typing import Any

from .pipeline import Pipeline
from ..config.settings import Settings
from ..ingestion.base import IngestionSource
from ..mapping.mapping_engine import MappingEngine
from ..ocsf.assembler import OCSFAssembler
from ..output.connector import OutputConnector
from ..output.jsonl_connector import JSONLConnector
from ..output.multi_connector import MultiConnector
from ..output.stdout_connector import StdoutConnector
from ..registry.extension_registry import ExtensionRegistry
from ..routing.event_router import EventRouter


def create_pipeline(
    settings: Settings,
    source_path: Path | None = None,
    output_path: Path | None = None,
    source_hint: str | None = None,
    output_mode: str = "jsonl",
    source: IngestionSource | None = None,
) -> Pipeline:
    """
    Convenience factory: reads config, instantiates all components, returns configured Pipeline.
    Used by both CLI and web API so they share identical behavior.
    """
    # 1. Extension Registry
    registry = ExtensionRegistry()
    ext_config_path = Path(settings.pipeline.extensions_config)
    if ext_config_path.exists():
        registry.load_from_config(ext_config_path)

    # 2. Event Router
    router = EventRouter(registry)

    # 3. Mapping Engine
    mapping_engine = MappingEngine()
    mappings_dir = Path(settings.pipeline.mappings_dir)
    if mappings_dir.exists():
        mapping_engine.load_directory(mappings_dir)

    # 4. OCSF Assembler
    assembler = OCSFAssembler()

    # 5. Output Connector
    target_out_path = output_path or (Path(settings.pipeline.output_dir) / "events.jsonl")
    connector: OutputConnector

    match output_mode.lower():
        case "stdout":
            connector = StdoutConnector()
        case "both":
            jsonl_conn = JSONLConnector(
                target_out_path,
                max_file_size_mb=settings.pipeline.max_output_file_size_mb,
            )
            stdout_conn = StdoutConnector()
            connector = MultiConnector([jsonl_conn, stdout_conn])
        case _:
            connector = JSONLConnector(
                target_out_path,
                max_file_size_mb=settings.pipeline.max_output_file_size_mb,
            )

    # 6. Ingestion Source (if source passed or source_path provided)
    active_source = source
    if active_source is None and source_path is not None:
        # Lazy import FileIngestionSource to avoid circular deps
        from ..ingestion.file_source import FileIngestionSource

        active_source = FileIngestionSource(
            file_path=source_path,
            source_hint=source_hint,
        )

    return Pipeline(
        source=active_source,
        router=router,
        registry=registry,
        mapping_engine=mapping_engine,
        ocsf_assembler=assembler,
        connector=connector,
        max_payload_bytes=settings.pipeline.max_payload_bytes,
        max_in_flight_batches=settings.pipeline.max_in_flight_batches,
    )

