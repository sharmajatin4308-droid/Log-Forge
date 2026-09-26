# LogForge — Architecture Specification
## Universal Security Log Pre-processing & Normalization Framework (ULPF)
**SIH Problem Statement:** PS 26156 · **Organization:** NTRO · **Team:** Hacked · **Canonical Standard:** OCSF 1.4.0

---

## 1. Executive Summary & Mission
Security Operations Centers (SOCs) and threat intelligence units ingest millions of heterogeneous logs daily from disparate network firewalls, servers, routers, and appliances. Existing SIEM ingestion pipelines suffer from vendor lock-in, brittle regex parsers, and silent field drops.

**LogForge** solves this through a zero-vendor-lock, micro-kernel architecture:
> LogForge converts heterogeneous security and network logs into OCSF 1.4.0 normalized events with complete raw event preservation and full processing lineage, using a zero-vendor-in-core micro-kernel and plug-and-play parser extensions.

---

## 2. Architectural Invariants (Core Guarantees)
The LogForge architecture enforces six strict invariants verified continuously via automated tests:

1. **Zero Format/Vendor Logic in Core (`I1` & `I2`):** `src/ulpf/` contains zero format names, vendor identifiers, regexes, or parsing heuristics. All parsing logic is strictly encapsulated in external extensions (`extensions/`).
2. **Standard Output Schema (`I3`):** Every normalized event adheres to the Open Cybersecurity Schema Framework (OCSF 1.4.0, Network Activity class 4001).
3. **Lossless Raw Event Preservation (`I4`):** The raw log byte-string is preserved unmodified in both `ocsf_event.raw_data` and the envelope `raw_event.payload`.
4. **Complete Lineage Tracking (`I5`):** Every record contains `ulpf_metadata` detailing the exact parser ID, version, mapping profile ID, duration, and parse status (`success`, `partial`, `failed`).
5. **Zero Data Loss (`I6`):** Any unmapped vendor attributes are preserved in `ocsf_event.unmapped`. No field is silently discarded.
6. **Pipeline Fault-Tolerance:** Malformed or corrupted logs never crash the pipeline; they are safely caught, tagged, and surfaced in the dead-letter / partial flow.

---

## 3. End-to-End Processing Pipeline

```
┌─────────────────┐
│ Ingestion Source│ (File / Stdin / HTTP)
└────────┬────────┘
         │ RawEvent
         ▼
┌─────────────────┐
│  Event Router   │ Phase 1: Explicit Override / Signal Scoring (Prefix, Contains, Regex)
└────────┬────────┘ Phase 2: Candidate Ranking & can_process() Confirmation
         │ Selected ParserExtension
         ▼
┌─────────────────┐
│ Parser Extension│ External plug-and-play extension extracts vendor key-value pairs
└────────┬────────┘
         │ ExtractedFields
         ▼
┌─────────────────┐
│ Mapping Engine  │ Loads YAML MappingProfile, applies type coercions & activity rules
└────────┬────────┘
         │ (ocsf_fields, unmapped)
         ▼
┌─────────────────┐
│ OCSF Assembler  │ Constructs OCSFNetworkActivity (4001) & validates types
└────────┬────────┘
         │ OCSFNetworkActivity
         ▼
┌─────────────────┐
│Output Connector │ Wraps into ULPFRecord envelope {ocsf_event, ulpf_metadata, raw_event}
└─────────────────┘ Emits to JSONL (NDJSON) or STDOUT
```

---

## 4. Component Taxonomy & Responsibilities

### 4.1 Ingestion Layer (`src/ulpf/ingestion/`)
- Normalizes disparate transport mechanisms (log files, UNIX pipelines via stdin, REST API endpoints) into unified `RawEvent` objects.
- Attaches UTC monotonic sequence timestamps and optional routing hints.

### 4.2 Two-Phase Routing Layer (`src/ulpf/routing/`)
- Avoids expensive trial-and-error parsing across hundreds of extensions.
- **Phase 1 (Cheap Detection):** Evaluates lightweight signatures (`prefix`, `contains`, `regex`, transport) and orders candidate extensions by specificity/priority.
- **Phase 2 (Confirmation):** Calls `can_process()` only on top-ranked candidates (max 5 candidates). If none match, safely falls back to `generic_ext`.

### 4.3 External Extension Registry (`src/ulpf/registry/` & `extensions/`)
- Dynamic plugin registry loaded via `config/extensions.yaml`.
- Adding a new format or vendor requires zero modifications to LogForge Core: simply drop a new extension module into `extensions/`, add a YAML mapping profile, and declare it in `config/extensions.yaml`.
- Default bundled extensions: Syslog (RFC 5424/BSD), JSON, CEF (ArcSight), Cisco ASA, and Generic Passthrough.

### 4.4 Declarative Mapping Engine (`src/ulpf/mapping/`)
- In-memory hot-path evaluation of frozen `MappingProfile` structures.
- Translates extracted vendor keys into dot-annotated OCSF paths (e.g., `src_ip` → `src_endpoint.ip`, `dst_port` → `dst_endpoint.port`).
- Evaluates dynamic firewall rules to assign canonical OCSF `action_id` (1=Allowed, 2=Denied) and `disposition_id`.

### 4.5 Canonical OCSF Assembler (`src/ulpf/ocsf/`)
- Assembles valid `OCSFNetworkActivity` records conforming to schema version 1.4.0.
- Guarantees top-level schema attributes: `class_uid: 4001`, `category_uid: 4`, `activity_id`, `severity_id`, `time`, and `metadata`.

### 4.6 Output & Lineage Envelope (`src/ulpf/output/`)
- Writes self-contained `ULPFRecord` JSON envelopes:
  - `ocsf_event`: Normalized cybersecurity event.
  - `ulpf_metadata`: End-to-end processing provenance and timings.
  - `raw_event`: Complete original payload and ingestion metadata for legal/forensic chain of custody.

---

## 5. Benchmark Performance
On standard commodity hardware (Windows 11 / Python 3.12):
- **Throughput:** > 11,000 events/second (exceeding SIH target of 5,000 EPS).
- **Latency (P50):** 0.071 ms / event.
- **Latency (P95):** 0.108 ms / event.
- **Success Rate:** 100% on sample validation corpora.
