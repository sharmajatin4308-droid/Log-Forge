// LogForge Event Inspector Modal Module
// Deep forensic examination of a single processed ULPFRecord

import { api } from '../api.js';
import { state, createSafeElement, copyToClipboard, formatTimestamp, announceAria } from '../state.js';
import { icons, getIcon } from '../icons.js';

let modalBackdrop = null;

export function initInspector() {
  modalBackdrop = document.getElementById('inspector-modal-backdrop');
  if (!modalBackdrop) return;

  // Click outside to close
  modalBackdrop.addEventListener('click', (e) => {
    if (e.target === modalBackdrop) {
      closeInspector();
    }
  });

  // Escape key to close
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.inspector.isOpen) {
      closeInspector();
    }
  });
}

/**
 * Opens inspector by event ID (fetches record) or with existing record
 * @param {string} rawEventId
 * @param {HTMLElement} [triggerElement]
 * @param {object} [existingRecord]
 */
export async function openInspector(rawEventId, triggerElement = null, existingRecord = null) {
  if (!modalBackdrop) {
    modalBackdrop = document.getElementById('inspector-modal-backdrop');
  }
  if (!modalBackdrop) return;

  state.inspector.isOpen = true;
  state.inspector.triggerElement = triggerElement;
  state.inspector.record = existingRecord;
  state.inspector.advancedViewOpen = false;

  modalBackdrop.classList.add('open');
  document.body.style.overflow = 'hidden';

  const modalContainer = document.getElementById('inspector-modal-content');
  if (!modalContainer) return;

  if (existingRecord) {
    renderInspectorContent(modalContainer, existingRecord);
    return;
  }

  // Fetch record from API
  modalContainer.innerHTML = `
    <div style="padding: 40px; text-align: center; color: var(--color-text-secondary);">
      <div class="skeleton" style="width: 60px; height: 60px; border-radius: 50%; margin: 0 auto 16px auto;"></div>
      <p style="font-size: 0.95rem;">Retrieving forensic record for <span style="font-family: var(--font-mono); color: var(--ink-title);">${rawEventId}</span>...</p>
    </div>
  `;

  try {
    const record = await api.event(rawEventId);
    state.inspector.record = record;
    renderInspectorContent(modalContainer, record);
    announceAria(`Inspecting event ${rawEventId}`);
  } catch (err) {
    console.error('Failed to load event:', err);
    renderInspectorError(modalContainer, err, rawEventId);
  }
}

export function closeInspector() {
  if (!modalBackdrop) return;
  modalBackdrop.classList.remove('open');
  document.body.style.overflow = '';
  state.inspector.isOpen = false;

  // Restore focus for accessibility
  if (state.inspector.triggerElement && typeof state.inspector.triggerElement.focus === 'function') {
    state.inspector.triggerElement.focus();
  }
}

function renderInspectorError(container, err, rawEventId) {
  container.innerHTML = '';

  const errBox = createSafeElement('div', '', 'glass-card', { style: 'margin: 20px; text-align: center; padding: 40px 20px;' });
  const icon = createSafeElement('div', '', '', { style: 'color: var(--jewel-error); margin-bottom: 14px;' });
  icon.innerHTML = getIcon('failed');

  const title = createSafeElement('h3', err.status === 404 ? 'Event Not Found' : 'Unable to Retrieve Event', '', {
    style: 'font-size: 1.2rem; color: var(--ink-title); margin-bottom: 8px;'
  });

  const msg = createSafeElement('p', err.status === 404
    ? `Event UUID ${rawEventId} was not found in the active output/events.jsonl. It may have rotated out or the server was restarted.`
    : err.message, 'section-description', { style: 'margin-bottom: 20px;' });

  const closeBtn = createSafeElement('button', 'Close Inspector', 'btn btn-secondary');
  closeBtn.addEventListener('click', closeInspector);

  errBox.append(icon, title, msg, closeBtn);
  container.appendChild(errBox);
}

function renderInspectorContent(container, record) {
  container.innerHTML = '';

  const meta = record.ulpf_metadata || {};
  const ocsf = record.ocsf_event || {};
  const raw = record.raw_event || {};
  const status = meta.parse_status || 'unknown';

  // Construct readable forensic summary
  const src = ocsf.src_endpoint?.ip ? `${ocsf.src_endpoint.ip}${ocsf.src_endpoint.port ? ':' + ocsf.src_endpoint.port : ''}` : '';
  const dst = ocsf.dst_endpoint?.ip ? `${ocsf.dst_endpoint.ip}${ocsf.dst_endpoint.port ? ':' + ocsf.dst_endpoint.port : ''}` : '';
  const proto = ocsf.connection_info?.protocol_name || '';
  const action = ocsf.action || ocsf.activity_name || '';
  const ext = meta.extension_id || 'Security Event';

  let summaryText = `${ext} event`;
  if (action) summaryText += ` (${action})`;
  if (src && dst) summaryText += `: ${src} → ${dst}`;
  if (proto) summaryText += ` [${proto}]`;

  // Header Row
  const header = createSafeElement('div', '', 'modal-header');
  const titleGroup = createSafeElement('div', '', 'modal-title-group');
  const h3 = createSafeElement('h3', 'Event Forensic Inspection');
  const summaryLine = createSafeElement('div', summaryText, 'modal-summary-line');
  titleGroup.append(h3, summaryLine);

  const headerRight = createSafeElement('div', '', '', { style: 'display: flex; align-items: center; gap: 12px;' });
  const statusBadge = createSafeElement('span', '', `status-badge badge-${status}`);
  const iconName = status === 'success' ? 'success' : status === 'partial' ? 'warning' : 'failed';
  statusBadge.innerHTML = `${getIcon(iconName)} ${status.toUpperCase()}`;

  const closeBtn = createSafeElement('button', '', 'btn btn-ghost btn-sm', {
    'aria-label': 'Close modal',
    style: 'padding: 6px;'
  });
  closeBtn.innerHTML = getIcon('close');
  closeBtn.addEventListener('click', closeInspector);

  headerRight.append(statusBadge, closeBtn);
  header.append(titleGroup, headerRight);

  // Body
  const body = createSafeElement('div', '', 'modal-body');

  // Diagnostic Parse Errors (if any)
  if (meta.parse_errors && meta.parse_errors.length > 0) {
    const errorBox = createSafeElement('div', '', 'error-alert-box');
    const errTitle = createSafeElement('div', '', 'error-alert-title');
    errTitle.innerHTML = `${getIcon('warning')} Parsing Errors (${meta.parse_errors.length}):`;
    const errList = createSafeElement('ul', '', 'error-list');
    meta.parse_errors.forEach(e => {
      errList.appendChild(createSafeElement('li', e));
    });
    errorBox.append(errTitle, errList);
    body.appendChild(errorBox);
  }

  // 1. Normalized OCSF Key Attributes Grid
  const ocsfSectionTitle = createSafeElement('h4', 'OCSF 1.4.0 Normalization (Class 4001 Network Activity)', 'form-label', {
    style: 'margin-bottom: 10px; color: var(--bronze-base);'
  });
  body.appendChild(ocsfSectionTitle);

  const ocsfGrid = createSafeElement('div', '', 'ocsf-fields-group');
  const ocsfFields = [
    { label: 'Activity', val: `${ocsf.activity_name || 'Unknown'} (ID: ${ocsf.activity_id ?? '0'})`, mono: false },
    { label: 'Severity', val: `${ocsf.severity || 'Unknown'} (ID: ${ocsf.severity_id ?? '—'})`, mono: false },
    { label: 'Action / Disposition', val: `${ocsf.action || '—'} / ${ocsf.disposition || '—'}`, mono: false },
    { label: 'Protocol', val: ocsf.connection_info?.protocol_name || '—', mono: true },
    { label: 'Source Endpoint', val: src || '—', mono: true },
    { label: 'Destination Endpoint', val: dst || '—', mono: true },
    { label: 'Traffic Direction', val: ocsf.connection_info?.direction || '—', mono: false },
    { label: 'Normalized Timestamp', val: formatTimestamp(ocsf.time, ocsf.metadata?.original_time), mono: true }
  ];

  ocsfFields.forEach(f => {
    const item = createSafeElement('div', '', 'ocsf-field-item');
    item.append(createSafeElement('div', f.label, 'ocsf-field-label'), createSafeElement('div', f.val, f.mono ? 'ocsf-field-val mono' : 'ocsf-field-val'));
    ocsfGrid.appendChild(item);
  });
  body.appendChild(ocsfGrid);

  // 2. Lineage & Provenance
  const lineageTitle = createSafeElement('h4', 'Processing Lineage & Provenance', 'form-label', {
    style: 'margin-top: 18px; margin-bottom: 10px; color: var(--bronze-base);'
  });
  body.appendChild(lineageTitle);

  const lineageTable = createSafeElement('table', '', 'lineage-table');
  const lineageRows = [
    { key: 'Event UUID', val: meta.raw_event_id || '—', copyable: true },
    { key: 'Parser / Version', val: `${meta.extension_id || 'unknown'} (v${meta.extension_version || '1.0.0'})` },
    { key: 'Mapping Profile', val: `${meta.mapping_profile_id || '—'} (v${meta.mapping_profile_version || '1.0'})` },
    { key: 'Duration', val: `${(meta.processing_duration_ms || 0).toFixed(3)} ms` },
    { key: 'Processed At (UTC)', val: meta.processed_at || '—' },
    { key: 'Ingest Transport', val: meta.transport || 'http' },
    { key: 'Source Hint Used', val: meta.source_hint_used || 'None (Auto-detected)' }
  ];

  lineageRows.forEach(r => {
    const tr = createSafeElement('tr');
    tr.append(createSafeElement('td', r.key, 'lineage-key'));
    const tdVal = createSafeElement('td', '', 'lineage-val');
    if (r.copyable) {
      const span = createSafeElement('span', r.val, '', { style: 'margin-right: 8px;' });
      const cpBtn = createSafeElement('button', 'Copy UUID', 'btn btn-secondary btn-sm', { type: 'button' });
      cpBtn.addEventListener('click', () => copyToClipboard(r.val, cpBtn));
      tdVal.append(span, cpBtn);
    } else {
      tdVal.textContent = r.val;
    }
    tr.appendChild(tdVal);
    lineageTable.appendChild(tr);
  });
  body.appendChild(lineageTable);

  // 3. Cryptographic Integrity Hash
  const hashBox = createSafeElement('div', '', '', {
    style: 'margin-top: 16px; padding: 12px 14px; background: var(--surface-plate); border: 1px solid rgba(141, 102, 19, 0.28); border-radius: var(--radius-sm);'
  });
  const hashLabel = createSafeElement('div', '', 'form-label', { style: 'margin-bottom: 6px; display: flex; align-items: center; gap: 6px;' });
  hashLabel.innerHTML = `${getIcon('shield')} SHA-256 Payload Hash (Forensic Authenticity)`;

  const hashRow = createSafeElement('div', '', '', { style: 'display: flex; gap: 10px; align-items: center;' });
  const hashPill = createSafeElement('div', '', 'hash-badge', { style: 'flex: 1;' });
  hashPill.appendChild(createSafeElement('span', meta.raw_payload_hash || '—', 'hash-text'));

  const cpHashBtn = createSafeElement('button', 'Copy Hash', 'btn btn-secondary btn-sm', { type: 'button' });
  cpHashBtn.addEventListener('click', () => copyToClipboard(meta.raw_payload_hash || '', cpHashBtn));
  hashRow.append(hashPill, cpHashBtn);
  hashBox.append(hashLabel, hashRow);
  body.appendChild(hashBox);

  // 4. Preserved Raw Payload
  const rawTitle = createSafeElement('h4', 'Preserved Raw Log Input (Character-for-Character)', 'form-label', {
    style: 'margin-top: 18px; margin-bottom: 8px;'
  });
  const rawPre = createSafeElement('pre', raw.payload || '', 'code-surface', {
    style: 'max-height: 140px; overflow-y: auto; color: var(--terminal-text);'
  });
  body.append(rawTitle, rawPre);

  // 5. Unmapped Fields
  const unmapped = ocsf.unmapped || {};
  const unmappedKeys = Object.keys(unmapped);
  const unmappedTitle = createSafeElement('h4', `Unmapped Vendor Fields (${unmappedKeys.length})`, 'form-label', {
    style: 'margin-top: 18px; margin-bottom: 8px;'
  });
  body.appendChild(unmappedTitle);

  if (unmappedKeys.length === 0) {
    const p = createSafeElement('p', 'No unmapped fields recorded. All vendor fields were converted to canonical OCSF.', 'section-description', {
      style: 'font-style: italic;'
    });
    body.appendChild(p);
  } else {
    const unmappedTable = createSafeElement('table', '', 'unmapped-table');
    const thead = createSafeElement('thead');
    const headerTr = createSafeElement('tr');
    headerTr.append(createSafeElement('th', 'Vendor Key'), createSafeElement('th', 'Value'));
    thead.appendChild(headerTr);
    const tbody = createSafeElement('tbody');
    unmappedKeys.forEach(k => {
      const tr = createSafeElement('tr');
      tr.append(createSafeElement('td', k), createSafeElement('td', typeof unmapped[k] === 'object' ? JSON.stringify(unmapped[k]) : String(unmapped[k])));
      tbody.appendChild(tr);
    });
    unmappedTable.append(thead, tbody);
    body.appendChild(unmappedTable);
  }

  // 6. Advanced Technical View (Collapsible)
  const advancedWrapper = createSafeElement('div', '', '', { style: 'margin-top: 24px;' });
  const toggleAdvBtn = createSafeElement('button', 'Show Advanced / Raw JSON View', 'btn btn-secondary btn-sm', {
    type: 'button',
    style: 'margin-bottom: 12px;'
  });

  const advContainer = createSafeElement('div', '', '', { style: 'display: none;' });

  toggleAdvBtn.addEventListener('click', () => {
    const isHidden = advContainer.style.display === 'none';
    advContainer.style.display = isHidden ? 'block' : 'none';
    toggleAdvBtn.textContent = isHidden ? 'Hide Advanced / Raw JSON View' : 'Show Advanced / Raw JSON View';
  });

  // Complete Record JSON Viewer
  const fullJsonLabel = createSafeElement('div', 'Complete ULPF Record JSON', 'form-label', { style: 'margin-bottom: 6px;' });
  const fullJsonPre = createSafeElement('pre', JSON.stringify(record, null, 2), 'code-surface', {
    style: 'max-height: 320px; overflow-y: auto;'
  });
  const copyRecordBtn = createSafeElement('button', 'Copy Full Record JSON', 'btn btn-secondary btn-sm', {
    type: 'button',
    style: 'margin-top: 8px;'
  });
  copyRecordBtn.addEventListener('click', () => copyToClipboard(JSON.stringify(record, null, 2), copyRecordBtn));

  advContainer.append(fullJsonLabel, fullJsonPre, copyRecordBtn);
  advancedWrapper.append(toggleAdvBtn, advContainer);
  body.appendChild(advancedWrapper);

  // Footer Row
  const footer = createSafeElement('div', '', 'modal-footer');
  const copyAllBtn = createSafeElement('button', 'Copy OCSF JSON', 'btn btn-secondary', { type: 'button' });
  copyAllBtn.innerHTML = `${getIcon('copy')} Copy OCSF JSON`;
  copyAllBtn.addEventListener('click', () => copyToClipboard(JSON.stringify(ocsf, null, 2), copyAllBtn));

  const dismissBtn = createSafeElement('button', 'Dismiss', 'btn btn-primary', { type: 'button' });
  dismissBtn.addEventListener('click', closeInspector);

  footer.append(copyAllBtn, dismissBtn);

  container.append(header, body, footer);
  dismissBtn.focus();
}
