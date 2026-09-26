import pytest
from datetime import datetime, timezone
from ulpf.pipeline.pipeline import Pipeline
from ulpf.models.raw_event import RawEvent
from ulpf.models.ingestion import IngestionMeta
from ulpf.ingestion.base import IngestionSource

class MockSource(IngestionSource):
    def __init__(self, payloads):
        self.payloads = payloads

    @property
    def source_id(self): return "mock_source"

    def close(self): pass

    def events(self):
        for i, p in enumerate(self.payloads):
            yield RawEvent(
                raw_event_id=f"evt_{i}",
                payload=p,
                ingestion=IngestionMeta(
                    source_id="test_source",
                    ingestion_sequence=i,
                    received_at=datetime.now(timezone.utc),
                    source_hint="test",
                    transport="test"
                )
            )

class MockConnector:
    def __init__(self):
        self.records = []
    
    def write(self, record):
        self.records.append(record)
        
    def flush(self):
        pass

# Dummy mocks for pipeline deps
class DummyRouter:
    def route(self, raw): return "generic"

class DummyRegistry:
    def get(self, ext_id): 
        from ulpf.registry.extension_registry import ExtensionRegistry
        r = ExtensionRegistry()
        r.discover()
        return r.get("generic")

class DummyMappingEngine:
    def get_profile(self, p_id): return None
    def map(self, ext, prof): return {}, {}

class DummyAssembler:
    def assemble(self, raw, ext, prof, ocsf, unmapped, errs, ts):
        from ulpf.models.ocsf.network_activity import OCSFNetworkActivity
        from ulpf.models.ocsf.metadata import OCSFMetadata
        return OCSFNetworkActivity(
            class_uid=4001, category_uid=4, type_uid=400100, activity_id=0,
            severity_id=0, time=0, raw_data=raw.payload, unmapped=unmapped,
            metadata=OCSFMetadata(version="1.4.0", product={"name": "test"}, uid=raw.raw_event_id)
        ), errs

def make_pipeline(payloads, max_batch_bytes=100, batch_size=3):
    source = MockSource(payloads)
    connector = MockConnector()
    pipeline = Pipeline(
        source=source,
        router=DummyRouter(),
        registry=DummyRegistry(),
        mapping_engine=DummyMappingEngine(),
        ocsf_assembler=DummyAssembler(),
        connector=connector,
        max_batch_bytes=max_batch_bytes
    )
    return pipeline, connector

def test_batching_exactly_at_limit():
    # max 100 bytes, batch size 3
    # 3 events of 33, 33, 34 bytes = 100 bytes exactly. Should be 1 batch.
    payloads = ["a"*33, "b"*33, "c"*34]
    p, c = make_pipeline(payloads, max_batch_bytes=100, batch_size=3)
    p.run_parallel(max_workers=1, executor_type="process", batch_size=3)
    assert len(c.records) == 3
    assert [r.raw_event.payload for r in c.records] == payloads

def test_batching_just_over_limit():
    # 33, 33, 35 = 101 bytes. The 35 byte one should trigger a new batch.
    # Total events: 3. Batches: [33, 33] (66b) and [35] (35b).
    payloads = ["a"*33, "b"*33, "c"*35]
    p, c = make_pipeline(payloads, max_batch_bytes=100, batch_size=3)
    p.run_parallel(max_workers=1, executor_type="process", batch_size=3)
    assert len(c.records) == 3
    assert [r.raw_event.payload for r in c.records] == payloads

def test_batching_one_large_event():
    # 1 event of 150 bytes (over max_batch_bytes).
    # Since batch is empty, it MUST be allowed in.
    payloads = ["a"*150]
    p, c = make_pipeline(payloads, max_batch_bytes=100, batch_size=3)
    p.run_parallel(max_workers=1, executor_type="process", batch_size=3)
    assert len(c.records) == 1

def test_batching_mixed_sizes():
    # 10, 80, 50, 10
    # Batch 1: 10 + 80 = 90. Next is 50, exceeds 100. Flush.
    # Batch 2: 50 + 10 = 60. End.
    payloads = ["a"*10, "b"*80, "c"*50, "d"*10]
    p, c = make_pipeline(payloads, max_batch_bytes=100, batch_size=3)
    p.run_parallel(max_workers=1, executor_type="process", batch_size=3)
    assert len(c.records) == 4
    assert [r.raw_event.payload for r in c.records] == payloads

def test_batching_count_limit_reached_first():
    # 10, 10, 10, 10
    # batch_size=3. So [10, 10, 10] (30b) -> flush due to count. [10].
    payloads = ["a"*10, "b"*10, "c"*10, "d"*10]
    p, c = make_pipeline(payloads, max_batch_bytes=100, batch_size=3)
    p.run_parallel(max_workers=1, executor_type="process", batch_size=3)
    assert len(c.records) == 4
    assert [r.raw_event.payload for r in c.records] == payloads

def test_batching_thread_executor():
    # thread executor ignores batching size but should still process all.
    payloads = ["a"*10, "b"*80, "c"*50, "d"*10]
    p, c = make_pipeline(payloads, max_batch_bytes=100, batch_size=3)
    p.run_parallel(max_workers=2, executor_type="thread", batch_size=3)
    # Thread executor doesn't guarantee order if there are multiple workers and short tasks,
    # but with our current wait logic and 1 worker, it might. We just check count and contents.
    assert len(c.records) == 4
    extracted_payloads = sorted([r.raw_event.payload for r in c.records])
    assert extracted_payloads == sorted(payloads)

def test_batching_zero_loss_zero_dups_order():
    payloads = [str(i)*50 for i in range(100)] # 100 events, 50 bytes each
    p, c = make_pipeline(payloads, max_batch_bytes=120, batch_size=10)
    # 120 bytes max -> 2 events per batch (100b), 3rd event (150b) pushes it over.
    # So it should do 50 batches of 2.
    p.run_parallel(max_workers=1, executor_type="process", batch_size=10)
    
    assert len(c.records) == 100
    assert [r.raw_event.payload for r in c.records] == payloads
