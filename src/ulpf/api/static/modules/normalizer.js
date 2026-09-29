// LogForge Interactive Normalizer Module (P0 Core Demo)
// Strict zero-innerHTML implementation for all backend and log strings

import { api } from '../api.js';
import { state, createSafeElement, copyToClipboard, formatTimestamp, announceAria } from '../state.js';
import { icons, getIcon } from '../icons.js';

export const SAMPLE_PRESETS = {
  'cisco-asa': 'Sep 01 12:30:05 fw01 %ASA-4-106001: Inbound TCP connection denied from 10.0.0.4/54321 to 8.8.8.8/53 flags SYN on interface outside',
  'syslog': '<134>Sep 01 12:30:05 fw01 action=deny src=10.0.0.4 dst=8.8.8.8 dpt=53 proto=UDP msg="Firewall dropped UDP packet"',
  'cef': 'CEF:0|Cisco|ASA|9.8.1|106001|Deny inbound TCP|5|src=10.0.0.4 spt=54321 dst=8.8.8.8 dpt=53 proto=TCP act=deny',
  'json': '{"timestamp": "2024-09-01T12:30:05Z", "src_ip": "10.0.0.4", "destination_ip": "8.8.8.8", "port": 53, "protocol": "UDP", "action": "deny"}'
};

export function initNormalizer() {
  const container = document.getElementById('tab-normalizer');
  if (!container) return;

  renderNormalizerView(container);
  updateSourceHintOptions();

  // If there was a previous result in state, render it
  if (state.normalizer.result) {
    renderResult(state.normalizer.result);
  }
}

function renderNormalizerView(container) {
  container.innerHTML = ''; // Initial shell setup

  // Section Header
  const header = createSafeElement('div', '', 'section-header');
  const titleGroup = createSafeElement('div', '', 'section-title-group');
  const title = createSafeElement('h2', '');
  title.innerHTML = `${getIcon('normalizer')} Interactive Normalizer`;
  const desc = createSafeElement('p', 'Paste any raw security log to observe automatic format routing, zero-data-loss extraction, OCSF 1.4.0 normalization, and cryptographic SHA-256 lineage tracking.', 'section-description');
  titleGroup.append(title, desc);
  header.appendChild(titleGroup);

  // Input Card
  const inputCard = createSafeElement('div', '', 'glass-card');
  const inputCardHeader = createSafeElement('div', '', 'section-header', { style: 'margin-bottom: 14px;' });
  const inputLabel = createSafeElement('label', 'Raw Security Log Payload', 'form-label', { for: 'normalizer-input' });

  // Presets Bar
  const presetsGroup = createSafeElement('div', '', 'preset-pills-bar');
  const presetLabel = createSafeElement('span', 'Presets:', 'form-label', { style: 'margin-right: 4px;' });
  presetsGroup.appendChild(presetLabel);

  const presets = [
    { id: 'cisco-asa', name: 'Cisco ASA Firewall' },
    { id: 'syslog', name: 'Syslog (BSD/RFC 5424)' },
    { id: 'cef', name: 'ArcSight CEF' },
    { id: 'json', name: 'Structured JSON' }
  ];

  presets.forEach(p => {
    const btn = createSafeElement('button', p.name, 'preset-pill', { type: 'button' });
    btn.addEventListener('click', () => {
      setPreset(p.id);
    });
    presetsGroup.appendChild(btn);
  });

  inputCardHeader.append(inputLabel, presetsGroup);

  // Textarea
  const textarea = createSafeElement('textarea', state.normalizer.input, 'form-textarea', {
    id: 'normalizer-input',
    rows: '4',
    placeholder: 'Paste raw log event (e.g. Syslog, CEF, Cisco ASA, JSON, or any proprietary log)...'
  });

  // Character Counter
  const charCounter = createSafeElement('div', `${state.normalizer.input.length} characters`, 'char-counter', { id: 'normalizer-char-count' });
  textarea.addEventListener('input', (e) => {
    state.normalizer.input = e.target.value;
    charCounter.textContent = `${e.target.value.length} characters`;
  });

  // Form Controls Row
  const controlsRow = createSafeElement('div', '', 'form-row', {
    style: 'display: flex; justify-content: space-between; align-items: flex-end; margin-top: 16px; flex-wrap: wrap; gap: 14px;'
  });

  // Source Hint Dropdown
  const hintGroup = createSafeElement('div', '', 'form-group', { style: 'min-width: 260px;' });
  const hintLabel = createSafeElement('label', 'Source Hint Override (Optional)', 'form-label', { for: 'normalizer-source-hint' });
  const hintSelect = createSafeElement('select', '', 'form-select', { id: 'normalizer-source-hint' });
  const autoOption = createSafeElement('option', 'Auto-detect format (Recommended)', '', { value: '' });
  hintSelect.appendChild(autoOption);

  hintSelect.addEventListener('change', (e) => {
    state.normalizer.sourceHint = e.target.value || null;
  });
  hintGroup.append(hintLabel, hintSelect);

  // Actions Button
  const actionsGroup = createSafeElement('div', '', 'form-actions', { style: 'display: flex; gap: 10px;' });

  const clearBtn = createSafeElement('button', 'Clear', 'btn btn-secondary', { type: 'button' });
  clearBtn.addEventListener('click', () => {
    textarea.value = '';
    state.normalizer.input = '';
    charCounter.textContent = '0 characters';
    const resultContainer = document.getElementById('normalizer-result-container');
    if (resultContainer) resultContainer.style.display = 'none';
    state.normalizer.result = null;
  });

  const processBtn = createSafeElement('button', 'Process & Normalize', 'btn btn-primary', {
    id: 'btn-process-normalizer',
    type: 'button'
  });
  processBtn.innerHTML = `${getIcon('lightning')} Process & Normalize`;
  processBtn.addEventListener('click', () => {
    handleProcessLog();
  });

  actionsGroup.append(clearBtn, processBtn);
  controlsRow.append(hintGroup, actionsGroup);

  // Error Alert Area
  const inlineError = createSafeElement('div', '', 'error-alert-box', {
    id: 'normalizer-inline-error',
    style: 'display: none; margin-top: 16px;'
  });

  inputCard.append(inputCardHeader, textarea, charCounter, controlsRow, inlineError);

  // Results Container (hidden initially)
  const resultContainer = createSafeElement('div', '', 'normalizer-result-container', {
    id: 'normalizer-result-container',
    style: 'display: none;'
  });

  container.append(header, inputCard, resultContainer);
}

export function updateSourceHintOptions() {
  const select = document.getElementById('normalizer-source-hint');
  if (!select) return;

  // Keep auto-detect as first option
  select.innerHTML = '<option value="">Auto-detect format (Recommended)</option>';

  if (state.extensions && state.extensions.length > 0) {
    state.extensions.forEach(ext => {
      const opt = createSafeElement('option', `${ext.extension_id} (${ext.description || ext.format_id})`, '', {
        value: ext.extension_id
      });
      if (state.normalizer.sourceHint === ext.extension_id) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
  }
}

export function setPreset(key) {
  const text = SAMPLE_PRESETS[key];
  if (!text) return;

  const textarea = document.getElementById('normalizer-input');
  const charCounter = document.getElementById('normalizer-char-count');
  if (textarea) {
    textarea.value = text;
    state.normalizer.input = text;
    if (charCounter) {
      charCounter.textContent = `${text.length} characters`;
    }
  }
}

export function setSourceHint(hintId) {
  state.normalizer.sourceHint = hintId;
  const select = document.getElementById('normalizer-source-hint');
  if (select) {
    select.value = hintId || '';
  }
}

async function handleProcessLog() {
  const textarea = document.getElementById('normalizer-input');
  const payload = textarea ? textarea.value.trim() : '';
  const errorBox = document.getElementById('normalizer-inline-error');
  const processBtn = document.getElementById('btn-process-normalizer');
  const resultContainer = document.getElementById('normalizer-result-container');

  if (errorBox) errorBox.style.display = 'none';

  if (!payload) {
    if (errorBox) {
      errorBox.textContent = 'Please enter a raw security log or select one of the sample presets.';
      errorBox.style.display = 'block';
    }
    textarea?.focus();
    return;
  }

  // 2MB size guard check on client
  if (new Blob([payload]).size > 2097152) {
    if (errorBox) {
      errorBox.textContent = 'Payload exceeds maximum limit of 2 MB. Please submit a smaller event.';
      errorBox.style.display = 'block';
    }
    return;
  }

  state.normalizer.loading = true;
  if (processBtn) {
    processBtn.disabled = true;
    processBtn.innerHTML = `<span class="skeleton" style="display:inline-block; width:14px; height:14px; border-radius:50%; margin-right:8px;"></span> Processing...`;
  }

  try {
    const record = await api.ingest(payload, state.normalizer.sourceHint);
    state.normalizer.result = record;
    renderResult(record);
    announceAria(`Processing complete: status is ${record.ulpf_metadata?.parse_status || 'completed'}`);
  } catch (err) {
    console.error('Ingest error:', err);
    if (errorBox) {
      errorBox.textContent = err.message || 'Failed to process log event.';
      errorBox.style.display = 'block';
    }
    if (resultContainer) {
      resultContainer.style.display = 'none';
    }
  } finally {
    state.normalizer.loading = false;
    if (processBtn) {
      processBtn.disabled = false;
      processBtn.innerHTML = `${getIcon('lightning')} Process & Normalize`;
    }
  }
}

function renderResult(record) {
  const container = document.getElementById('normalizer-result-container');
  if (!container) return;

  container.innerHTML = '';
  container.style.display = 'block';

  const meta = record.ulpf_metadata || {};
  const ocsf = record.ocsf_event || {};
  const raw = record.raw_event || {};
  const status = meta.parse_status || 'unknown';

  // 1. Result Header Bar with Status Badge and Latency
  const resultHeader = createSafeElement('div', '', 'glass-card', {
    style: 'display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; margin-bottom: 20px; flex-wrap: wrap; gap: 12px;'
  });

  const headerLeft = createSafeElement('div', '', '', { style: 'display: flex; align-items: center; gap: 14px;' });
  const statusTitle = createSafeElement('span', 'Transformation Result:', 'form-label', { style: 'font-size: 0.9rem;' });

  const statusBadge = createSafeElement('span', '', `status-badge badge-${status}`);
  const iconName = status === 'success' ? 'success' : status === 'partial' ? 'warning' : 'failed';
  statusBadge.innerHTML = `${getIcon(iconName)} ${status.toUpperCase()}`;

  headerLeft.append(statusTitle, statusBadge);

  const headerRight = createSafeElement('div', '', '', { style: 'display: flex; align-items: center; gap: 16px;' });
  const latencyBadge = createSafeElement('div', '', '', {
    style: 'display: flex; align-items: center; gap: 6px; font-family: var(--font-mono); font-size: 0.85rem; color: var(--bronze-base);'
  });
  latencyBadge.innerHTML = `${getIcon('clock')} ${(meta.processing_duration_ms || 0).toFixed(2)} ms latency`;

  headerRight.appendChild(latencyBadge);
  resultHeader.append(headerLeft, headerRight);
  container.appendChild(resultHeader);

  // 2. Parse Errors Banner (if any)
  if (meta.parse_errors && meta.parse_errors.length > 0) {
    const errorCard = createSafeElement('div', '', 'error-alert-box');
    const errTitle = createSafeElement('div', '', 'error-alert-title');
    errTitle.innerHTML = `${getIcon('warning')} Parsing Diagnostic Notes (${meta.parse_errors.length}):`;
    const errList = createSafeElement('ul', '', 'error-list');

    meta.parse_errors.forEach(errMsg => {
      const li = createSafeElement('li', errMsg);
      errList.appendChild(li);
    });

    errorCard.append(errTitle, errList);
    container.appendChild(errorCard);
  }

  // 3. Two-Column Result Grid
  const grid = createSafeElement('div', '', 'normalizer-result-grid');

  // LEFT COLUMN: Detection, Lineage & Cryptographic Integrity
  const leftCol = createSafeElement('div', '', 'left-column');

  const lineageCard = createSafeElement('div', '', 'glass-card');
  const lineageHeader = createSafeElement('div', '', 'section-header', { style: 'margin-bottom: 12px;' });
  const lineageTitle = createSafeElement('h3', '', '', { style: 'font-size: 1.05rem; font-weight: 700;' });
  lineageTitle.innerHTML = `${getIcon('lineage')} Detection & Lineage Provenance`;
  lineageHeader.appendChild(lineageTitle);

  const lineageTable = createSafeElement('table', '', 'lineage-table');
  const rows = [
    { key: 'Assigned Event ID', val: meta.raw_event_id || '—', copyable: true },
    { key: 'Detected Parser', val: `${meta.extension_id || 'unknown'} (v${meta.extension_version || '1.0.0'})` },
    { key: 'Mapping Profile', val: `${meta.mapping_profile_id || '—'} (v${meta.mapping_profile_version || '1.0'})` },
    { key: 'OCSF Schema', val: `v${meta.schema_version || '1.4.0'} (Class 4001 Network Activity)` },
    { key: 'Source Hint Used', val: meta.source_hint_used || 'None (Auto-detected)' },
    { key: 'Ingest Transport', val: meta.transport || 'http' },
    { key: 'Processed At', val: meta.processed_at ? new Date(meta.processed_at).toUTCString() : '—' }
  ];

  rows.forEach(r => {
    const tr = createSafeElement('tr');
    const tdKey = createSafeElement('td', r.key, 'lineage-key');
    const tdVal = createSafeElement('td', '', 'lineage-val');

    if (r.copyable) {
      const valSpan = createSafeElement('span', r.val, '', { style: 'margin-right: 8px;' });
      const copyBtn = createSafeElement('button', 'Copy', 'btn btn-secondary btn-sm', { type: 'button' });
      copyBtn.addEventListener('click', () => copyToClipboard(r.val, copyBtn));
      tdVal.append(valSpan, copyBtn);
    } else {
      tdVal.textContent = r.val;
    }
    tr.append(tdKey, tdVal);
    lineageTable.appendChild(tr);
  });

  // Integrity section within left column
  const integrityBlock = createSafeElement('div', '', '', {
    style: 'margin-top: 18px; padding-top: 16px; border-top: 1px solid rgba(141, 102, 19, 0.28);'
  });
  const integrityTitle = createSafeElement('div', '', 'form-label', { style: 'margin-bottom: 8px; display: flex; align-items: center; gap: 6px;' });
  integrityTitle.innerHTML = `${getIcon('shield')} SHA-256 Payload Hash (Chain of Custody)`;

  const hashRow = createSafeElement('div', '', '', { style: 'display: flex; gap: 8px; align-items: center;' });
  const hashPill = createSafeElement('div', '', 'hash-badge', { style: 'flex: 1;' });
  const hashSpan = createSafeElement('span', meta.raw_payload_hash || '—', 'hash-text');
  hashPill.appendChild(hashSpan);

  const copyHashBtn = createSafeElement('button', 'Copy Hash', 'btn btn-secondary btn-sm', { type: 'button' });
  copyHashBtn.addEventListener('click', () => copyToClipboard(meta.raw_payload_hash || '', copyHashBtn));
  hashRow.append(hashPill, copyHashBtn);

  integrityBlock.append(integrityTitle, hashRow);
  lineageCard.append(lineageHeader, lineageTable, integrityBlock);
  leftCol.appendChild(lineageCard);

  // Unmapped Fields Card (Zero data loss proof)
  const unmappedCard = createSafeElement('div', '', 'glass-card');
  const unmappedHeader = createSafeElement('div', '', 'section-header', { style: 'margin-bottom: 12px;' });
  const unmappedTitle = createSafeElement('h3', 'Unmapped Vendor Fields', '', { style: 'font-size: 1.05rem; font-weight: 700; color: #191106 !important;' });
  unmappedHeader.appendChild(unmappedTitle);

  const unmapped = ocsf.unmapped || {};
  const unmappedKeys = Object.keys(unmapped);

  if (unmappedKeys.length === 0) {
    const emptyNote = createSafeElement('p', 'No unmapped fields. All extracted vendor attributes mapped directly into standard OCSF attributes.', 'section-description', {
      style: 'font-style: italic; color: var(--ink-muted);'
    });
    unmappedCard.append(unmappedHeader, emptyNote);
  } else {
    const unmappedTable = createSafeElement('table', '', 'unmapped-table');
    const thead = createSafeElement('thead');
    const headerRow = createSafeElement('tr');
    headerRow.append(createSafeElement('th', 'Vendor Key'), createSafeElement('th', 'Extracted Value'));
    thead.appendChild(headerRow);

    const tbody = createSafeElement('tbody');
    unmappedKeys.forEach(k => {
      const tr = createSafeElement('tr');
      const tdK = createSafeElement('td', k);
      const tdV = createSafeElement('td', typeof unmapped[k] === 'object' ? JSON.stringify(unmapped[k]) : String(unmapped[k]));
      tr.append(tdK, tdV);
      tbody.appendChild(tr);
    });

    unmappedTable.append(thead, tbody);
    unmappedCard.append(unmappedHeader, unmappedTable);
  }
  leftCol.appendChild(unmappedCard);

  // RIGHT COLUMN: Normalized OCSF Event Structure
  const rightCol = createSafeElement('div', '', 'right-column');
  const ocsfCard = createSafeElement('div', '', 'glass-card');

  const ocsfHeader = createSafeElement('div', '', 'section-header', { style: 'margin-bottom: 16px;' });
  const ocsfTitle = createSafeElement('h3', '', '', { style: 'font-size: 1.05rem; font-weight: 700;' });
  ocsfTitle.innerHTML = `${getIcon('inspect')} Normalized OCSF 1.4.0 Network Activity`;

  const copyOcsfBtn = createSafeElement('button', 'Copy OCSF JSON', 'btn btn-secondary btn-sm', { type: 'button' });
  copyOcsfBtn.innerHTML = `${getIcon('copy')} Copy OCSF JSON`;
  copyOcsfBtn.addEventListener('click', () => {
    copyToClipboard(JSON.stringify(ocsf, null, 2), copyOcsfBtn);
  });

  ocsfHeader.append(ocsfTitle, copyOcsfBtn);

  // Structured OCSF Attributes Grid
  const ocsfGrid = createSafeElement('div', '', 'ocsf-fields-group');

  const srcIp = ocsf.src_endpoint?.ip || '—';
  const srcPort = ocsf.src_endpoint?.port != null ? `:${ocsf.src_endpoint.port}` : '';
  const dstIp = ocsf.dst_endpoint?.ip || '—';
  const dstPort = ocsf.dst_endpoint?.port != null ? `:${ocsf.dst_endpoint.port}` : '';

  const fields = [
    { label: 'Activity Name', val: ocsf.activity_name || 'Unknown', mono: false },
    { label: 'Action / Disposition', val: `${ocsf.action || '—'} / ${ocsf.disposition || '—'}`, mono: false },
    { label: 'Severity', val: `${ocsf.severity || 'Unknown'} (ID: ${ocsf.severity_id ?? '—'})`, mono: false },
    { label: 'Protocol', val: ocsf.connection_info?.protocol_name || '—', mono: true },
    { label: 'Source Endpoint', val: `${srcIp}${srcPort}`, mono: true },
    { label: 'Destination Endpoint', val: `${dstIp}${dstPort}`, mono: true },
    { label: 'Traffic Direction', val: ocsf.connection_info?.direction || '—', mono: false },
    { label: 'Normalized Time', val: formatTimestamp(ocsf.time, ocsf.metadata?.original_time), mono: true }
  ];

  fields.forEach(f => {
    const item = createSafeElement('div', '', 'ocsf-field-item');
    const lbl = createSafeElement('div', f.label, 'ocsf-field-label');
    const val = createSafeElement('div', f.val, f.mono ? 'ocsf-field-val mono' : 'ocsf-field-val');
    item.append(lbl, val);
    ocsfGrid.appendChild(item);
  });

  // Full OCSF Pretty JSON Viewer
  const jsonLabel = createSafeElement('div', 'Complete OCSF Event JSON Payload', 'form-label', { style: 'margin-top: 14px; margin-bottom: 6px;' });
  const ocsfJsonPre = createSafeElement('pre', JSON.stringify(ocsf, null, 2), 'code-surface', {
    style: 'max-height: 380px; overflow-y: auto;'
  });

  ocsfCard.append(ocsfHeader, ocsfGrid, jsonLabel, ocsfJsonPre);
  rightCol.appendChild(ocsfCard);

  grid.append(leftCol, rightCol);
  container.appendChild(grid);

  // 4. Immutable Raw Event Preservation Block (Ground Truth)
  const rawCard = createSafeElement('div', '', 'glass-card', { style: 'margin-top: 20px;' });
  const rawHeader = createSafeElement('div', '', 'section-header', { style: 'margin-bottom: 12px;' });
  const rawTitle = createSafeElement('h3', '', '', { style: 'font-size: 1.05rem; font-weight: 700; color: #191106 !important;' });
  rawTitle.innerHTML = `${getIcon('terminal')} Immutable Raw Log Event (Character-for-Character Ground Truth)`;

  const copyRawBtn = createSafeElement('button', 'Copy Raw Payload', 'btn btn-secondary btn-sm', { type: 'button' });
  copyRawBtn.innerHTML = `${getIcon('copy')} Copy Raw`;
  copyRawBtn.addEventListener('click', () => {
    copyToClipboard(raw.payload || '', copyRawBtn);
  });

  rawHeader.append(rawTitle, copyRawBtn);

  const rawPre = createSafeElement('pre', raw.payload || '', 'code-surface', {
    style: 'max-height: 180px; overflow-y: auto; color: var(--terminal-text);'
  });

  rawCard.append(rawHeader, rawPre);
  container.appendChild(rawCard);
}
