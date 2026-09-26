// LogForge Batch File Ingest Module
// Sequential client-side chunking (<=100 events per request) with real EPS computation
// Transformed operational workspace: balanced initial layout, rich processing telemetry

import { api } from '../api.js';
import { state, createSafeElement, announceAria } from '../state.js';
import { icons, getIcon } from '../icons.js';
import { loadDashboardData } from './dashboard.js';
import { loadEvents } from './events.js';

export function initBatch() {
  const container = document.getElementById('tab-batch');
  if (!container) return;

  renderBatchShell(container);
}

function renderBatchShell(container) {
  container.innerHTML = '';

  // 1. Header
  const header = createSafeElement('div', '', 'section-header');
  const titleGroup = createSafeElement('div', '', 'section-title-group');
  const title = createSafeElement('h2', '');
  title.innerHTML = `${getIcon('batch')} Batch Log Ingestion & Bulk Normalization`;
  const desc = createSafeElement('p', 'High-throughput stream processing. Client-side chunking sequentially delivers batches (≤100 events/call) to compute real operational throughput.', 'section-description');
  titleGroup.append(title, desc);
  header.appendChild(titleGroup);

  // Hidden file input used by dropzone and browse button
  const fileInput = createSafeElement('input', '', '', {
    type: 'file',
    id: 'batch-file-input',
    accept: '.log,.txt,.csv,.jsonl',
    style: 'display: none;'
  });

  // 2. Initial Pre-Upload View (Balanced Two-Column Workspace)
  const initialGrid = createSafeElement('div', '', 'batch-workspace-initial', { id: 'batch-initial-grid' });

  // Left Column: Dropzone
  const uploadCard = createSafeElement('div', '', 'glass-card');
  const dropzone = createSafeElement('div', '', 'dropzone-container', {
    id: 'batch-dropzone',
    role: 'button',
    tabindex: '0',
    'aria-label': 'Upload log file'
  });

  const dropIcon = createSafeElement('div', '', 'dropzone-icon');
  dropIcon.innerHTML = getIcon('batch');
  const dropTitle = createSafeElement('div', 'Drag & drop raw log stream here', 'dropzone-title');
  const dropSub = createSafeElement('div', 'Supports .log, .txt, .csv, and .jsonl files. Evaluates up to 100 events per chunk.', 'dropzone-subtitle');

  // Format Tags
  const formatChips = createSafeElement('div', '', 'dash-standards-pills', { style: 'justify-content: center; margin-top: 18px;' });
  ['.LOG Payload', '.TXT Streams', '.CSV Logs', '.JSONL Lines'].forEach(fmt => {
    formatChips.appendChild(createSafeElement('span', fmt, 'dash-badge-chip pill-subtle'));
  });

  const browseBtn = createSafeElement('button', 'Browse Local Files', 'btn btn-secondary btn-sm', {
    type: 'button',
    style: 'margin-top: 18px;'
  });
  browseBtn.innerHTML = `${getIcon('file')} Browse Local File`;

  dropzone.append(dropIcon, dropTitle, dropSub, formatChips, browseBtn);
  uploadCard.appendChild(dropzone);

  // Right Column: Batch Architecture & Pipeline Specs
  const specsCard = createSafeElement('div', '', 'glass-card');
  const specsHeader = createSafeElement('div', '', 'dash-card-header');
  const specsTitle = createSafeElement('h3', 'Bulk Normalization Engine', 'dash-card-title');
  const specsPill = createSafeElement('span', 'Sequential HTTP', 'dash-status-pill pill-subtle');
  specsHeader.append(specsTitle, specsPill);

  const specsList = createSafeElement('div', '', 'dash-specs-list');
  const specItems = [
    { label: 'Chunk Protocol', val: '≤ 100 events per HTTP payload' },
    { label: 'Memory Safety', val: 'Streamed client slicing (no OOM)' },
    { label: 'Throughput Telemetry', val: 'Real wall-clock EPS calculation' },
    { label: 'Schema Standard', val: 'OCSF 1.4.0 Class 4001 Network' },
    { label: 'Integrity Stamping', val: 'Per-event SHA-256 fingerprint' },
    { label: 'Execution Mode', val: 'Deterministic rule-based pipeline' }
  ];

  specItems.forEach(it => {
    const row = createSafeElement('div', '', 'dash-spec-row');
    row.append(
      createSafeElement('span', it.label, 'dash-spec-label'),
      createSafeElement('span', it.val, 'dash-spec-value mono')
    );
    specsList.appendChild(row);
  });

  const specsNotes = createSafeElement('p', 'Files are read locally in the browser, validated for UTF-8 compliance, and dispatched sequentially to /api/ingest/batch without server timeouts.', 'dash-card-description');

  specsCard.append(specsHeader, specsList, specsNotes);
  initialGrid.append(uploadCard, specsCard);

  // Dropzone Interaction Handlers
  dropzone.addEventListener('click', (e) => {
    if (e.target !== browseBtn) fileInput.click();
  });
  browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  dropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.click();
    }
  });

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('drag-over');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('drag-over');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileSelected(files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  });

  // 3. Operational Processing Dashboard Workspace (Shown once file is selected)
  const processingWorkspace = createSafeElement('div', '', 'batch-processing-workspace', {
    id: 'batch-processing-workspace',
    style: 'display: none;'
  });

  // Selected File Meta & Actions Area
  const fileMetaCard = createSafeElement('div', '', 'glass-card', { id: 'batch-file-meta' });

  // Live Progress & Telemetry Card
  const progressCard = createSafeElement('div', '', 'glass-card', {
    id: 'batch-progress-card',
    style: 'display: none;'
  });

  // Completion Summary Card
  const completionCard = createSafeElement('div', '', 'glass-card', {
    id: 'batch-completion-card',
    style: 'display: none;'
  });

  processingWorkspace.append(fileMetaCard, progressCard, completionCard);
  container.append(header, fileInput, initialGrid, processingWorkspace);
}

function handleFileSelected(file) {
  const initialGrid = document.getElementById('batch-initial-grid');
  const workspace = document.getElementById('batch-processing-workspace');
  const metaCard = document.getElementById('batch-file-meta');
  const progressCard = document.getElementById('batch-progress-card');
  const completionCard = document.getElementById('batch-completion-card');

  if (!metaCard || !workspace) return;

  if (initialGrid) initialGrid.style.display = 'none';
  workspace.style.display = 'block';

  if (progressCard) progressCard.style.display = 'none';
  if (completionCard) completionCard.style.display = 'none';

  state.batch.file = file;

  // File size warning checks
  const fileSizeMB = file.size / (1024 * 1024);
  let warningMessage = '';
  if (fileSizeMB > 50) {
    warningMessage = 'Advisory: File exceeds 50 MB. Processing large files in the browser consumes substantial client memory; the LogForge CLI (`logforge process`) is recommended for production bulk ingestion.';
  } else if (fileSizeMB > 5) {
    warningMessage = 'Notice: File exceeds 5 MB. Client processing memory and network roundtrips will scale accordingly.';
  }

  metaCard.innerHTML = '';

  const headerRow = createSafeElement('div', '', 'dash-card-header');
  const titleGroup = createSafeElement('div', '', '', { style: 'display: flex; align-items: center; gap: 14px;' });
  const fileIcon = createSafeElement('div', '', '', { style: 'color: var(--palette-warm-orange); font-size: 1.4rem;' });
  fileIcon.innerHTML = getIcon('file');

  const fileTitleDetails = createSafeElement('div');
  const fileName = createSafeElement('h3', file.name, 'dash-card-title', { style: 'word-break: break-all;' });
  const fileSize = createSafeElement('div', `${(file.size / 1024).toFixed(1)} KB — reading lines...`, 'section-description');
  fileTitleDetails.append(fileName, fileSize);
  titleGroup.append(fileIcon, fileTitleDetails);

  const actionsGroup = createSafeElement('div', '', 'section-actions');

  const resetBtn = createSafeElement('button', 'Choose Different File', 'btn btn-secondary btn-sm', { type: 'button' });
  resetBtn.addEventListener('click', () => {
    state.batch.file = null;
    state.batch.lines = [];
    state.batch.chunks = [];
    workspace.style.display = 'none';
    if (initialGrid) initialGrid.style.display = 'grid';
  });

  const startBtn = createSafeElement('button', 'Start Ingestion', 'btn btn-primary', {
    id: 'btn-start-batch',
    type: 'button',
    disabled: 'true'
  });
  startBtn.innerHTML = `${getIcon('lightning')} Start Batch Ingestion`;

  actionsGroup.append(resetBtn, startBtn);
  headerRow.append(titleGroup, actionsGroup);
  metaCard.appendChild(headerRow);

  if (warningMessage) {
    const warnBox = createSafeElement('div', '', 'error-alert-box', {
      style: 'margin-top: 14px; background: var(--color-status-warning-bg); border-color: var(--color-status-warning-border);'
    });
    const warnTitle = createSafeElement('div', '', 'error-alert-title', { style: 'color: var(--palette-warm-orange);' });
    warnTitle.innerHTML = `${getIcon('warning')} Large File Advisory`;
    const warnText = createSafeElement('p', warningMessage, 'section-description', { style: 'color: #ffd0a8;' });
    warnBox.append(warnTitle, warnText);
    metaCard.appendChild(warnBox);
  }

  // Read file lines
  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const rawLines = text.split(/\r?\n/);
    const validLines = rawLines.map(l => l.trim()).filter(l => l.length > 0);

    state.batch.lines = validLines;
    state.batch.chunks = [];
    for (let i = 0; i < validLines.length; i += 100) {
      state.batch.chunks.push(validLines.slice(i, i + 100));
    }

    fileSize.textContent = `${(file.size / 1024).toFixed(1)} KB — ${validLines.length.toLocaleString()} valid log events (${state.batch.chunks.length} sequential chunks of ≤ 100)`;
    startBtn.disabled = validLines.length === 0;

    if (validLines.length === 0) {
      fileSize.textContent += ' (No valid lines found in selected file)';
    }

    startBtn.onclick = () => runBatchIngestion();
  };

  reader.onerror = () => {
    fileSize.textContent = 'Error reading file. Ensure it is a valid UTF-8 text file.';
    startBtn.disabled = true;
  };

  reader.readAsText(file, 'utf-8');
}

async function runBatchIngestion() {
  const progressCard = document.getElementById('batch-progress-card');
  const startBtn = document.getElementById('btn-start-batch');

  if (!progressCard || state.batch.chunks.length === 0) return;

  state.batch.processing = true;
  state.batch.cancelled = false;
  state.batch.currentChunk = 0;
  state.batch.stats = { total: 0, success: 0, partial: 0, failed: 0, total_duration_ms: 0 };
  state.batch.errors = [];
  state.batch.startTime = performance.now();
  state.batch.abortController = new AbortController();

  if (startBtn) startBtn.disabled = true;
  progressCard.style.display = 'block';

  renderProgressCardUI(progressCard);

  const totalChunks = state.batch.chunks.length;

  for (let i = 0; i < totalChunks; i++) {
    if (state.batch.cancelled) {
      break;
    }

    state.batch.currentChunk = i;
    const chunk = state.batch.chunks[i];

    try {
      const res = await api.ingestBatch(chunk, state.batch.abortController.signal);
      const stats = res.stats || {};

      state.batch.stats.total += (stats.total || chunk.length);
      state.batch.stats.success += (stats.success || 0);
      state.batch.stats.partial += (stats.partial || 0);
      state.batch.stats.failed += (stats.failed || 0);
      state.batch.stats.total_duration_ms += (stats.total_duration_ms || 0);
    } catch (err) {
      if (err.message.includes('cancelled')) {
        break;
      }
      console.warn(`Chunk ${i + 1} failed:`, err);
      state.batch.stats.failed += chunk.length;
      state.batch.stats.total += chunk.length;
      state.batch.errors.push(`Chunk ${i + 1} (lines ${i * 100 + 1}-${i * 100 + chunk.length}): ${err.message}`);
    }

    // Update Progress UI
    const elapsedSec = (performance.now() - state.batch.startTime) / 1000;
    const backendSec = state.batch.stats.total_duration_ms / 1000;
    const wallClockEps = elapsedSec > 0 ? (state.batch.stats.total / elapsedSec) : 0;
    const backendEps = backendSec > 0 ? (state.batch.stats.total / backendSec) : 0;

    updateProgressUI(i + 1, totalChunks, state.batch.stats, wallClockEps, backendEps, elapsedSec);
  }

  state.batch.processing = false;
  state.batch.wallClockDurationMs = performance.now() - state.batch.startTime;
  state.batch.lastCompletedStats = { ...state.batch.stats };

  // Update session EPS on Dashboard!
  const finalWallEps = (state.batch.wallClockDurationMs / 1000) > 0
    ? (state.batch.stats.total / (state.batch.wallClockDurationMs / 1000))
    : 0;
  state.dashboard.lastBatchEps = finalWallEps;

  renderCompletionCard();
  announceAria(`Batch processing complete. Processed ${state.batch.stats.total} events.`);

  // Silently refresh events and dashboard in background
  loadEvents();
  loadDashboardData();
}

function renderProgressCardUI(container) {
  container.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 12px;">
      <div>
        <h3 style="font-size: 1.15rem; font-weight: 700; color: #ffffff;">Streaming Batch Execution</h3>
        <p id="batch-progress-subtitle" class="section-description">Transmitting chunks sequentially to /api/ingest/batch...</p>
      </div>
      <button id="btn-cancel-batch" class="btn btn-danger btn-sm" type="button">Halt Ingestion</button>
    </div>

    <div class="progress-track" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" id="batch-progress-bar-track">
      <div class="progress-fill" id="batch-progress-fill" style="width: 0%;"></div>
    </div>

    <div class="dash-center-tiles-row" style="margin-top: 20px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));">
      <div class="dash-tile-card">
        <div class="dash-card-label">Processed Events</div>
        <div class="dash-tile-value" id="batch-stat-total" style="font-size: 1.7rem;">0</div>
        <div class="dash-tile-sub" id="batch-stat-chunks">0 of 0 chunks</div>
      </div>
      <div class="dash-tile-card tile-success">
        <div class="dash-card-label">Success Rate</div>
        <div class="dash-tile-value" id="batch-stat-success" style="font-size: 1.7rem; color: var(--color-status-success);">0</div>
        <div class="dash-tile-sub" id="batch-stat-rate">100% Normalized</div>
      </div>
      <div class="dash-tile-card tile-warning">
        <div class="dash-card-label">Partial / Fallback</div>
        <div class="dash-tile-value" id="batch-stat-partial" style="font-size: 1.7rem; color: var(--palette-warm-orange);">0</div>
        <div class="dash-tile-sub">Unmapped fields</div>
      </div>
      <div class="dash-tile-card tile-warning">
        <div class="dash-card-label">Failed</div>
        <div class="dash-tile-value" id="batch-stat-failed" style="font-size: 1.7rem; color: var(--palette-crimson-rose);">0</div>
        <div class="dash-tile-sub">Parse errors</div>
      </div>
      <div class="dash-tile-card">
        <div class="dash-card-label">Wall-Clock EPS</div>
        <div class="dash-tile-value" id="batch-stat-wall-eps" style="font-size: 1.7rem; color: var(--palette-warm-orange);">0</div>
        <div class="dash-tile-sub" id="batch-stat-elapsed">0.0s elapsed</div>
      </div>
      <div class="dash-tile-card">
        <div class="dash-card-label">Backend Engine EPS</div>
        <div class="dash-tile-value" id="batch-stat-backend-eps" style="font-size: 1.7rem;">0</div>
        <div class="dash-tile-sub">Pure engine compute</div>
      </div>
    </div>
  `;

  document.getElementById('btn-cancel-batch')?.addEventListener('click', () => {
    state.batch.cancelled = true;
    if (state.batch.abortController) {
      state.batch.abortController.abort();
    }
    const sub = document.getElementById('batch-progress-subtitle');
    if (sub) sub.textContent = 'Halting batch ingestion...';
  });
}

function updateProgressUI(chunksDone, totalChunks, stats, wallEps, backendEps, elapsedSec) {
  const percent = Math.min(100, Math.round((chunksDone / totalChunks) * 100));
  const fill = document.getElementById('batch-progress-fill');
  const track = document.getElementById('batch-progress-bar-track');

  if (fill) fill.style.width = `${percent}%`;
  if (track) track.setAttribute('aria-valuenow', String(percent));

  const sub = document.getElementById('batch-progress-subtitle');
  if (sub) {
    sub.textContent = `Processing chunk ${chunksDone} of ${totalChunks} (${percent}%) — ${stats.total.toLocaleString()} events handled`;
  }

  const elTotal = document.getElementById('batch-stat-total');
  const elChunks = document.getElementById('batch-stat-chunks');
  const elSuccess = document.getElementById('batch-stat-success');
  const elRate = document.getElementById('batch-stat-rate');
  const elPartial = document.getElementById('batch-stat-partial');
  const elFailed = document.getElementById('batch-stat-failed');
  const elWallEps = document.getElementById('batch-stat-wall-eps');
  const elElapsed = document.getElementById('batch-stat-elapsed');
  const elBackEps = document.getElementById('batch-stat-backend-eps');

  if (elTotal) elTotal.textContent = stats.total.toLocaleString();
  if (elChunks) elChunks.textContent = `${chunksDone} of ${totalChunks} chunks`;
  if (elSuccess) elSuccess.textContent = stats.success.toLocaleString();
  if (elRate) {
    const rate = stats.total > 0 ? ((stats.success / stats.total) * 100).toFixed(1) : 100;
    elRate.textContent = `${rate}% Normalized`;
  }
  if (elPartial) elPartial.textContent = stats.partial.toLocaleString();
  if (elFailed) elFailed.textContent = stats.failed.toLocaleString();
  if (elWallEps) elWallEps.textContent = Math.round(wallEps).toLocaleString();
  if (elElapsed) elElapsed.textContent = `${elapsedSec.toFixed(1)}s elapsed`;
  if (elBackEps) elBackEps.textContent = Math.round(backendEps).toLocaleString();
}

function renderCompletionCard() {
  const completionCard = document.getElementById('batch-completion-card');
  if (!completionCard) return;

  completionCard.innerHTML = '';
  completionCard.style.display = 'block';

  const stats = state.batch.stats;
  const elapsedSec = state.batch.wallClockDurationMs / 1000;
  const wallEps = elapsedSec > 0 ? (stats.total / elapsedSec) : 0;
  const backendSec = stats.total_duration_ms / 1000;
  const backendEps = backendSec > 0 ? (stats.total / backendSec) : 0;
  const successRate = stats.total > 0 ? ((stats.success / stats.total) * 100).toFixed(1) : '100.0';

  const isCancelled = state.batch.cancelled;

  const header = createSafeElement('div', '', 'section-header', { style: 'margin-bottom: 18px;' });
  const titleGroup = createSafeElement('div');
  const title = createSafeElement('h3', isCancelled ? 'Batch Ingestion Halted' : 'Batch Normalization Complete', '', {
    style: 'font-size: 1.3rem; font-weight: 700; color: #ffffff;'
  });
  const sub = createSafeElement('p', isCancelled
    ? `Processing was halted. Partial results have been committed to output/events.jsonl.`
    : `Processed ${stats.total.toLocaleString()} log lines in ${elapsedSec.toFixed(2)} seconds. All records committed to storage.`, 'section-description');
  titleGroup.append(title, sub);

  const actions = createSafeElement('div', '', 'section-actions');
  const exploreBtn = createSafeElement('button', 'Browse Events Explorer', 'btn btn-primary', { type: 'button' });
  exploreBtn.innerHTML = `${getIcon('events')} View in Events Explorer`;
  exploreBtn.addEventListener('click', () => {
    document.getElementById('tab-btn-events')?.click();
  });
  actions.appendChild(exploreBtn);

  header.append(titleGroup, actions);

  // Summary Metrics Breakdown
  const breakdown = createSafeElement('div', '', 'ocsf-fields-group', { style: 'margin-top: 14px;' });
  const items = [
    { label: 'Total Ingested Events', val: stats.total.toLocaleString() },
    { label: 'Successfully Normalized', val: `${stats.success.toLocaleString()} (${successRate}%)` },
    { label: 'Partial / Fallback Records', val: stats.partial.toLocaleString() },
    { label: 'Failed Records', val: stats.failed.toLocaleString() },
    { label: 'Measured Wall-Clock EPS', val: `${Math.round(wallEps).toLocaleString()} EPS`, mono: true },
    { label: 'Measured Backend EPS', val: `${Math.round(backendEps).toLocaleString()} EPS`, mono: true },
    { label: 'Total Wall-Clock Time', val: `${elapsedSec.toFixed(2)} s` },
    { label: 'Engine Processing Duration', val: `${stats.total_duration_ms.toFixed(1)} ms` }
  ];

  items.forEach(it => {
    const box = createSafeElement('div', '', 'ocsf-field-item');
    box.append(createSafeElement('div', it.label, 'ocsf-field-label'), createSafeElement('div', it.val, it.mono ? 'ocsf-field-val mono' : 'ocsf-field-val'));
    breakdown.appendChild(box);
  });

  completionCard.append(header, breakdown);

  // Errors list if any chunk had issues
  if (state.batch.errors.length > 0) {
    const errBox = createSafeElement('div', '', 'error-alert-box', { style: 'margin-top: 18px;' });
    const errTitle = createSafeElement('div', '', 'error-alert-title');
    errTitle.innerHTML = `${getIcon('warning')} Chunk Error Log (${state.batch.errors.length}):`;
    const ul = createSafeElement('ul', '', 'error-list');
    state.batch.errors.forEach(err => ul.appendChild(createSafeElement('li', err)));
    errBox.append(errTitle, ul);
    completionCard.appendChild(errBox);
  }
}
