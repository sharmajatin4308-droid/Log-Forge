from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
    FIRST_COMPLETED,
)
from datetime import datetime, timezone
import hashlib
import logging
import os
import time
from typing import Any

from ..config.settings import get_recommended_workers
from ..ingestion.base import IngestionSource
from ..mapping.mapping_engine import MappingEngine
from ..mapping.profile import MappingProfile
from ..models.extracted import ExtractedFields
from ..models.ocsf.metadata import OCSFMetadata, OCSFProduct
from ..models.ocsf.network_activity import OCSFNetworkActivity
from ..models.pipeline import PipelineStats
from ..models.raw_event import RawEvent
from ..models.ulpf_metadata import ULPFMetadata
from ..models.ulpf_record import ULPFRecord
from ..ocsf.assembler import OCSFAssembler, DEFAULT_OCSF_PRODUCT
from ..output.connector import OutputConnector
from ..registry.extension_registry import ExtensionRegistry
from ..routing.event_router import EventRouter

logger = logging.getLogger(__name__)


def _get_passthrough_profile(extension_id: str) -> MappingProfile:
    return MappingProfile(
        profile_id="generic_passthrough",
        profile_version="0.0.0",
        format_id="unknown",
        vendor=None,
        product=None,
        field_mappings={},
        type_coercions={},
        timestamp_config=None,
        activity_rules=[],
        observer_log_name="unknown",
    )


def _make_error_record(
    raw: RawEvent,
    error_msg: str,
    start_time: datetime,
    start_perf: float | None = None,
) -> ULPFRecord:
    if start_perf is not None:
        duration_ms = max(0.0, (time.perf_counter() - start_perf) * 1000.0)
    else:
        duration_ms = max(0.0, (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0)
    raw_hash = hashlib.sha256(raw.payload.encode("utf-8")).hexdigest()
    ocsf_metadata = OCSFMetadata(
        version="1.4.0",
        product=DEFAULT_OCSF_PRODUCT,
        uid=raw.raw_event_id,
    )
    ocsf_event = OCSFNetworkActivity(
        class_uid=4001,
        class_name="Network Activity",
        category_uid=4,
        category_name="Network Activity",
        activity_id=0,
        type_uid=400100,
        time=0,
        severity_id=0,
        raw_data=raw.payload,
        unmapped={"raw_payload": raw.payload},
        metadata=ocsf_metadata,
    )
    ulpf_meta = ULPFMetadata(
        raw_event_id=raw.raw_event_id,
        extension_id="generic",
        extension_version="1.0.0",
        mapping_profile_id="generic_passthrough",
        mapping_profile_version="0.0.0",
        schema_version="1.4.0",
        parse_status="failed",
        parse_errors=[error_msg],
        processed_at=start_time,
        processing_duration_ms=duration_ms,
        source_hint_used=raw.ingestion.source_hint,
        transport=raw.ingestion.transport,
        raw_payload_hash=raw_hash,
    )
    return ULPFRecord(
        ocsf_event=ocsf_event.model_dump(exclude_none=True),
        ulpf_metadata=ulpf_meta,
        raw_event=raw,
    )


class Pipeline:
    def __init__(
        self,
        source: IngestionSource | None,
        router: EventRouter,
        registry: ExtensionRegistry,
        mapping_engine: MappingEngine,
        ocsf_assembler: OCSFAssembler,
        connector: OutputConnector | None = None,
        max_payload_bytes: int = 2097152,
        max_in_flight_batches: int = 0,
        max_batch_bytes: int = 5242880,
    ) -> None:
        self.source = source
        self.router = router
        self.registry = registry
        self.mapping_engine = mapping_engine
        self.ocsf_assembler = ocsf_assembler
        self.connector = connector
        self.max_payload_bytes = max_payload_bytes
        self.max_in_flight_batches = max_in_flight_batches
        self.max_batch_bytes = max_batch_bytes

    def process_one(self, raw: RawEvent) -> ULPFRecord:
        """Process a single RawEvent. Never raises."""
        start_time = datetime.now(timezone.utc)
        start_perf = time.perf_counter()
        parse_status: str = "success"
        parse_errors: list[str] = []

        try:
            # Phase 1: Route
            extension_id = self.router.route(raw)
            extension = self.registry.get(extension_id) or self.registry.get("generic")

            if extension is None:
                raise RuntimeError(
                    f"Neither extension '{extension_id}' nor fallback 'generic' found in registry"
                )

            meta = extension.extension_metadata()

            # Phase 1.5: Payload size guard & integrity hash (computed once from preserved payload)
            encoded_payload = raw.payload.encode("utf-8")
            payload_bytes = len(encoded_payload)
            raw_hash = hashlib.sha256(encoded_payload).hexdigest()

            if payload_bytes > self.max_payload_bytes:
                parse_errors.append(
                    f"Payload size ({payload_bytes} bytes) exceeds max_payload_bytes ({self.max_payload_bytes})"
                )
                parse_status = "failed"
                extracted = ExtractedFields(
                    extension_id=extension_id,
                    extension_version=meta.extension_version,
                    fields={},
                    parse_confidence=0.0,
                )
            else:
                # Phase 2: Parse
                try:
                    extracted = extension.parse(raw)
                except Exception as e:
                    logger.warning("Parse error in extension '%s': %s", extension_id, e)
                    parse_errors.append(f"Parse error in {extension_id}: {e}")
                    parse_status = "failed"
                    extracted = ExtractedFields(
                        extension_id=extension_id,
                        extension_version=meta.extension_version,
                        fields={},
                        parse_confidence=0.0,
                    )

            # Phase 3: Determine mapping profile
            profile_id = extracted.mapping_profile_hint or meta.default_mapping_profile
            profile = self.mapping_engine.get_profile(profile_id)
            if profile is None:
                parse_errors.append(f"Mapping profile not found: {profile_id}")
                if parse_status == "success":
                    parse_status = "partial"
                profile = _get_passthrough_profile(extension_id)

            # Phase 4: Map
            if parse_status != "failed":
                ocsf_fields, unmapped = self.mapping_engine.map(extracted, profile)
            else:
                ocsf_fields = {}
                unmapped = {"raw_payload": raw.payload}

            # Downgrade to partial if confidence is low
            if extracted.parse_confidence < 0.5 and parse_status == "success":
                parse_status = "partial"

            # Phase 5: Assemble OCSF event
            ocsf_event, parse_errors = self.ocsf_assembler.assemble(
                raw, extracted, profile, ocsf_fields, unmapped, parse_errors, start_time
            )

            # Phase 6: Build ULPFMetadata
            duration_ms = max(0.0, (time.perf_counter() - start_perf) * 1000.0)
            ulpf_meta = ULPFMetadata(
                raw_event_id=raw.raw_event_id,
                extension_id=extension_id,
                extension_version=meta.extension_version,
                mapping_profile_id=profile.profile_id,
                mapping_profile_version=profile.profile_version,
                schema_version="1.4.0",
                parse_status=parse_status,  # type: ignore
                parse_errors=parse_errors,
                processed_at=start_time,
                processing_duration_ms=duration_ms,
                source_hint_used=raw.ingestion.source_hint,
                transport=raw.ingestion.transport,
                raw_payload_hash=raw_hash,
            )

            record = ULPFRecord(
                ocsf_event=ocsf_event.model_dump(exclude_none=True),
                ulpf_metadata=ulpf_meta,
                raw_event=raw,
            )

        except Exception as e:
            logger.error("Unexpected error in pipeline: %s", e, exc_info=True)
            parse_errors.append(f"Pipeline error: {e}")
            record = _make_error_record(raw, str(e), start_time, start_perf)

        if self.connector is not None:
            self.connector.write(record)

        return record

    def process_batch(self, batch: list[RawEvent]) -> list[ULPFRecord]:
        """
        Process a batch of raw events locally on a worker.
        Preserves existing per-event semantics and error isolation.
        """
        return [self.process_one(raw) for raw in batch]

    def run(self) -> PipelineStats:
        """Consume all events from source. Return aggregate stats."""
        stats = PipelineStats()
        pipeline_start_ns = time.perf_counter_ns()

        if self.source is not None:
            for raw in self.source.events():
                record = self.process_one(raw)
                stats.total += 1
                match record.ulpf_metadata.parse_status:
                    case "success":
                        stats.success += 1
                    case "partial":
                        stats.partial += 1
                    case "failed":
                        stats.failed += 1

        stats.total_duration_ms = (time.perf_counter_ns() - pipeline_start_ns) / 1_000_000.0
        if self.connector is not None:
            self.connector.flush()

        return stats

    def run_parallel(
        self,
        max_workers: int | None = None,
        executor_type: str = "process",
        batch_size: int = 100,
    ) -> PipelineStats:
        """
        Process events using a configurable Executor pool.

        Args:
            max_workers: Number of workers.
                         None or <= 0 = auto-detected physical cores (min 1).
            executor_type: "process" for ProcessPoolExecutor,
                           "thread" for ThreadPoolExecutor.
            batch_size: Number of raw events per batch in process executor mode (default: 100).

        Returns:
            Aggregated PipelineStats.
        """
        if max_workers is not None and max_workers <= 0:
            effective_workers = get_recommended_workers(executor_type)
        elif max_workers is None:
            effective_workers = get_recommended_workers(executor_type)
        else:
            effective_workers = max_workers

        effective_batch_size = batch_size if batch_size > 0 else 100

        if executor_type == "process" and effective_batch_size > 500 and effective_workers > 4:
            logger.warning(
                "Large batch_size (%d) with %d workers may cause high IPC memory usage and backpressure latency; consider batch_size between 100 and 200.",
                effective_batch_size,
                effective_workers,
            )

        stats = PipelineStats()
        pipeline_start_ns = time.perf_counter_ns()

        if self.source is None:
            return stats

        if executor_type == "process":
            # Batched multiprocessing: group raw events into batches of batch_size.
            # In process mode, workers cannot share the connector handle/lock.
            # process_batch is executed with connector=None on workers,
            # and the parent process writes records to main_connector upon harvesting completed futures.
            main_connector = self.connector
            self.connector = None
            if self.max_in_flight_batches and self.max_in_flight_batches > 0:
                max_in_flight_batches = self.max_in_flight_batches
            else:
                max_in_flight_batches = max(2, effective_workers * 2)

            try:
                with ProcessPoolExecutor(max_workers=effective_workers) as executor:
                    futures: set = set()
                    source_iter = iter(self.source.events())
                    source_exhausted = False
                    held_event = None

                    while not source_exhausted or futures or held_event:
                        # Refill up to max_in_flight_batches
                        while (not source_exhausted or held_event) and len(futures) < max_in_flight_batches:
                            batch: list[RawEvent] = []
                            batch_bytes = 0

                            if held_event is not None:
                                batch.append(held_event)
                                batch_bytes += len(held_event.payload.encode("utf-8"))
                                held_event = None

                            try:
                                while len(batch) < effective_batch_size:
                                    raw = next(source_iter)
                                    event_bytes = len(raw.payload.encode("utf-8"))
                                    
                                    if batch and (batch_bytes + event_bytes > self.max_batch_bytes):
                                        held_event = raw
                                        break
                                        
                                    batch.append(raw)
                                    batch_bytes += event_bytes
                            except StopIteration:
                                source_exhausted = True

                            if batch:
                                future = executor.submit(self.process_batch, batch)
                                futures.add(future)

                        if not futures:
                            break

                        # Wait for at least one batch future to complete (backpressure)
                        done, futures = wait(futures, return_when=FIRST_COMPLETED)

                        for future in done:
                            batch_records = future.result()
                            for record in batch_records:
                                if main_connector is not None:
                                    main_connector.write(record)

                                stats.total += 1
                                match record.ulpf_metadata.parse_status:
                                    case "success":
                                        stats.success += 1
                                    case "partial":
                                        stats.partial += 1
                                    case "failed":
                                        stats.failed += 1
            finally:
                self.connector = main_connector
        else:
            # Thread mode: preserve existing unbatched concurrent execution
            max_in_flight = effective_workers * 4
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                futures: set = set()
                source_iter = iter(self.source.events())
                source_exhausted = False

                while not source_exhausted or futures:
                    while not source_exhausted and len(futures) < max_in_flight:
                        try:
                            raw = next(source_iter)
                            future = executor.submit(self.process_one, raw)
                            futures.add(future)
                        except StopIteration:
                            source_exhausted = True

                    if not futures:
                        break

                    done, futures = wait(futures, return_when=FIRST_COMPLETED)

                    for future in done:
                        record = future.result()  # process_one never raises
                        stats.total += 1
                        match record.ulpf_metadata.parse_status:
                            case "success":
                                stats.success += 1
                            case "partial":
                                stats.partial += 1
                            case "failed":
                                stats.failed += 1

        stats.total_duration_ms = (time.perf_counter_ns() - pipeline_start_ns) / 1_000_000.0
        if self.connector is not None:
            self.connector.flush()

        return stats

