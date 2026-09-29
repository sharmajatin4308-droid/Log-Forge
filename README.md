# LogForge — Universal Security Log Pre-processing & Normalization Framework (ULPF)

> **Smart India Hackathon 2026 Submission** | **Problem Statement:** PS 26156 (NTRO) | **Team:** Team Hacked | **License:** [MIT License](LICENSE)


[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://python.org)
[![OCSF](https://img.shields.io/badge/Schema-OCSF%201.4.0-green.svg)](https://schema.ocsf.io)
[![Tests](https://img.shields.io/badge/Tests-135%20passed%20(100%25)-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/Core%20Coverage-88%25-brightgreen.svg)]()
[![Throughput](https://img.shields.io/badge/Throughput-12%2C359%20EPS-success.svg)]()

> **SIH Problem Statement:** PS 26156 · **Organization:** NTRO · **Team:** Hacked

**LogForge** is a high-performance, modular log preprocessing engine that converts heterogeneous security logs into normalized **OCSF 1.4.0** events with complete raw event preservation and full provenance lineage.

---

## Key Features & Highlights

- **Zero-Vendor-Lock Core:** `src/ulpf/` contains **zero** format-specific, vendor-specific, or regex parsing code. All parsers are plug-and-play external extensions (`extensions/`).
- **In-Process Parser Isolation:** Parser extensions execute in-process with strict Pydantic v2 schema validation, type enforcement, and boundary error handling. *(Note: LogForge uses in-process schema and error boundary isolation, not OS-level container sandboxing).*
- **Canonical OCSF 1.4.0 Standard:** Emits canonical OCSF class 4001 (`Network Activity`) records with standardized activity, disposition, severity, and network endpoints.
- **Two-Phase Routing Layer:** Lightweight signature matching (prefix, contains, regex) and candidate ranking select the correct parser in microseconds, eliminating trial-and-error parsing overhead.
- **Lossless & Forensic Lineage:** Preserves the un-altered original payload in both `ocsf_event.raw_data` and the `raw_event` envelope, along with SHA-256 payload hashes. Non-mappable vendor attributes are safely retained in `ocsf_event.unmapped`.
- **Fault Tolerant:** Malformed or unknown logs never crash the pipeline; fallback to the `generic` extension ensures continuous pipeline uptime.
- **Built-in Web Dashboard & API:** High-speed FastAPI server with an interactive log normalizer, event stream explorer, and extension registry inspector.
- **Authentication Status:** In this prototype and demonstration release, authentication is intentionally absent to facilitate immediate evaluation. Production deployments should position an authentication reverse proxy or API gateway (e.g., NGINX, OAuth2 Proxy) in front of the server.
- **AI Parser Onboarding Concept:** Includes a client-side interface preview for assisted regex and field mapping generation. *(Note: This is currently a UI concept preview rather than an active production LLM pipeline).*

---

## Quickstart Guide

### 1. One-Click Windows Quickstart (Recommended)

LogForge includes dedicated PowerShell lifecycle scripts designed for evaluator and production convenience.

#### First-Time Initialization (Run Once):
```powershell
# One-time setup: validates Python 3.12+, sets up isolated .venv, installs LogForge, and opens the Web UI
.\boot-logforge.ps1
```
> **Note:** `boot-logforge.ps1` is a **one-time setup operation**. A Windows reboot or closing the terminal does **not** require booting again.

#### Normal Everyday Launch:
```powershell
# Normal launcher: instant startup, opens the Web UI, zero reinstalling/dependency overhead
.\run-logforge.ps1
```

#### Custom Port Support:
```powershell
# Launch on an alternate port if 8000 is occupied
.\run-logforge.ps1 -Port 8080
```

---

### 2. Manual Cross-Platform Installation

If you prefer manual setup using [uv](https://github.com/astral-sh/uv) or standard Python virtual environments:

```bash
# Clone and enter the repository
cd logforge

# Using uv (Recommended for speed):
uv sync
uv pip install -e .

# Or using standard Python:
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### 2. Processing Logs via CLI

```bash
# Process a syslog file and display execution statistics
logforge process samples/syslog/sample_001.log --stats

# Process Cisco ASA logs and output directly to stdout
logforge process samples/cisco_asa/sample_001.log --output stdout

# Stream logs from stdin via standard UNIX pipes
cat samples/cef/sample_001.log | logforge process - --output stdout
```

### 3. Validating OCSF Compliance

Validate generated JSONL output against the canonical OCSF 1.4.0 schema:

```bash
logforge validate output/events.jsonl
```

### 4. Running Benchmarks via CLI

Benchmark pipeline throughput and latency percentiles on local log corpora:

```bash
# Sequential benchmark with latency percentiles (P50, P95, P99)
logforge bench samples/syslog/large.log

# Multi-worker parallel benchmark
logforge bench samples/benchmark_10k_mixed.log --workers 4
```

### 5. Launching the Web UI & API Server

```bash
logforge serve --host 127.0.0.1 --port 8000
```

Open your browser at `http://127.0.0.1:8000`:
- **Dashboard:** Real-time event statistics, throughput metrics, and pipeline health.
- **Interactive Process:** Paste raw security logs, select optional hints, and inspect real-time normalized OCSF records and metadata lineage.
- **Events Explorer:** Browse, filter (success/partial/failed), and inspect recently processed log events stored in `output/events.jsonl`.
- **Extensions View:** Inspect registered parser extensions, versioning, and detection priority.
- **OpenAPI Documentation:** Interactive Swagger UI available at `http://127.0.0.1:8000/docs`.

---

## Performance Benchmarks

The following throughput figures represent the official comparable benchmark set measured on a dedicated multi-core test machine under standardized in-memory benchmark conditions.

To evaluate core pipeline normalization throughput independently of storage subsystem bottlenecks, processing was conducted using an in-memory/no-op connector across a fixed 100,000-event syslog workload.

### Verified Throughput Results

| Configuration | Throughput | Target (SIH PS26156) | Status |
|---|---:|---|---|
| **1 Worker** (Sequential) | **7,400 events/sec** | ≥ 5,000 EPS | Exceeded (+48%) |
| **4 Workers** (Parallel IPC) | **12,359 events/sec** | ≥ 5,000 EPS | Exceeded (+147%) |
| **8 Workers** (Parallel IPC) | **10,585 events/sec** | ≥ 5,000 EPS | Exceeded (+111%) |

*Note: The 1, 4, and 8 worker measurements constitute the verified comparable benchmark set. Throughput peaks at 4 workers (12,359 EPS) on this hardware architecture due to optimal cache locality and IPC queue saturation.*

### Benchmark Environment & Hardware Specifications

The benchmark results were empirically verified on the following hardware platform:

- **System Model:** Lenovo LOQ (83JC)
- **CPU:** AMD Ryzen 7 7435HS (8 physical cores, 16 logical threads, up to 4.5 GHz boost)
- **Architecture:** x86-64 (AMD64 Family 25 Model 68 Stepping 1)
- **System Memory (RAM):** 24.0 GB DDR5
- **Operating System:** Microsoft Windows 11 Home Single Language (64-bit, Build 26200)
- **Python Version:** Python 3.12.10 (CPython, 64-bit)
- **Workload Corpus:** 100,000 events (`samples/syslog/benchmark_100k.log`)
- **Workers Tested:** 1, 4, and 8
- **IPC Mechanism:** Multiprocessing (`ProcessPoolExecutor`) with batched IPC chunking
- **Batch Size:** 100 events per IPC task
- **Output Connector:** In-memory / no-op connector (measures pipeline-only processing speed; excludes disk I/O latency)

> **Performance Disclaimer:** These figures represent measured execution results under the specific test configuration described above. They do not constitute universal throughput guarantees. Real-world performance will vary depending on log event complexity, schema depth, storage I/O speeds, and host hardware.

---

## Supported Format Extensions

| Extension ID | Format Family | Priority | Default Mapping Profile | Status |
|---|---|---|---|---|
| `cisco-asa` | Cisco ASA Firewall | 10 (High) | `cisco_asa` | Bundled |
| `cef` | ArcSight CEF | 20 | `cef_standard` | Bundled |
| `json` | Structured JSON | 30 | `json_generic` | Bundled |
| `syslog` | RFC 5424 / BSD Syslog | 50 | `syslog_generic` | Bundled |
| `generic` | Unknown / Fallback | 100 (Lowest) | `generic_passthrough` | Bundled |

---

## Air-Gapped & Containerized Deployment

LogForge has **zero runtime dependencies on external cloud services or databases**.

### Docker Build & Run

```bash
# Build the container image
docker build -t logforge:latest .

# Run the web API server on port 8000
docker run -p 8000:8000 logforge:latest
```

Health check verification:
```bash
curl http://localhost:8000/api/health
# {"status":"ok","version":"1.0.0","ocsf_version":"1.4.0","uptime_seconds":...}
```

---

## Architectural Invariant Verification

Run the automated test suite to verify all architectural invariants and regression suites:

```bash
python -m pytest tests/ -v
```

All **135 automated tests pass** with **88% test coverage** across the core processing engine (`src/ulpf`).
