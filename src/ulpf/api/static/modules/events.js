// LogForge Events Explorer Module
// Forensic log browsing, filtering, and pagination against /api/events

import { api } from '../api.js';
import { state, createSafeElement, formatTimestamp, announceAria } from '../state.js';
import { icons, getIcon } from '../icons.js';
import { openInspector } from './inspector.js';
import { loadDashboardData } from './dashboard.js';

export function initEventsExplorer() {
  const container = document.getElementById('tab-events');
  if (!container) return;

  setupClearEventsModalListeners();
  renderEventsExplorerShell(container);
  loadEvents();
}

function setupClearEventsModalListeners() {
  const modalBackdrop = document.getElementById('clear-events-modal-backdrop');
  if (modalBackdrop && !modalBackdrop._hasListener) {
    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop) {
        closeClearConfirmationModal();
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modalBackdrop.classList.contains('open')) {
        closeClearConfirmationModal();
      }
    });
    modalBackdrop._hasListener = true;
  }
}

function renderEventsExplorerShell(container) {
  container.innerHTML = '';

  // Header
  const header = createSafeElement('div', '', 'section-header');
  const titleGroup = createSafeElement('div', '', 'section-title-group');
  const title = createSafeElement('h2', '');
  title.innerHTML = `${getIcon('events')} Stored Events Explorer`;
  const desc = createSafeElement('p', 'Browse, filter, and inspect canonical OCSF 1.4.0 events stored in the immutable JSONL stream.', 'section-description');
  titleGroup.append(title, desc);

  // Filters & Controls Bar
  const actions = createSafeElement('div', '', 'section-actions');

  // Status Filter
  const statusSelect = createSafeElement('select', '', 'form-select', {
    id: 'events-filter-status',
    'aria-label': 'Filter events by parse status'
  });
  const optAll = createSafeElement('option', 'All Statuses', '', { value: '' });
  const optSuccess = createSafeElement('option', 'Success Only', '', { value: 'success' });
  const optPartial = createSafeElement('option', 'Partial / Fallback', '', { value: 'partial' });
  const optFailed = createSafeElement('option', 'Failed Only', '', { value: 'failed' });
  statusSelect.append(optAll, optSuccess, optPartial, optFailed);

  if (state.events.status) {
    statusSelect.value = state.events.status;
  }

  statusSelect.addEventListener('change', (e) => {
    state.events.status = e.target.value || null;
    state.events.offset = 0;
    loadEvents();
  });

  // Page Size Select
  const limitSelect = createSafeElement('select', '', 'form-select', {
    id: 'events-filter-limit',
    'aria-label': 'Rows per page'
  });
  [25, 50, 100].forEach(l => {
    const opt = createSafeElement('option', `${l} per page`, '', { value: String(l) });
    if (state.events.limit === l) opt.selected = true;
    limitSelect.appendChild(opt);
  });

  limitSelect.addEventListener('change', (e) => {
    state.events.limit = parseInt(e.target.value, 10) || 25;
    state.events.offset = 0;
    loadEvents();
  });

  // Refresh Button
  const refreshBtn = createSafeElement('button', 'Refresh', 'btn btn-secondary', {
    id: 'btn-events-refresh',
    type: 'button'
  });
  refreshBtn.innerHTML = `${getIcon('refresh')} Refresh`;
  refreshBtn.addEventListener('click', () => {
    loadEvents();
  });

  actions.append(statusSelect, limitSelect, refreshBtn);
  header.append(titleGroup, actions);

  // Alerts & Notifications Banner Container
  const bannerContainer = createSafeElement('div', '', 'events-banner-wrapper', { id: 'events-banner-container' });

  // Table Container
  const tableContainer = createSafeElement('div', '', 'table-container');
  const table = createSafeElement('table', '', 'data-table');

  const thead = createSafeElement('thead');
  const headerRow = createSafeElement('tr');
  const cols = ['Event UUID', 'Parser', 'Profile', 'Status', 'Source IP', 'Dest IP', 'Action', 'Timestamp', 'Inspect'];
  cols.forEach(colName => {
    const th = createSafeElement('th', colName, '', { scope: 'col' });
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  const tbody = createSafeElement('tbody', '', '', { id: 'events-table-tbody' });
  table.append(thead, tbody);
  tableContainer.appendChild(table);

  // Pagination Footer
  const paginationBar = createSafeElement('div', '', 'pagination-bar', { id: 'events-pagination-bar' });
  const pageInfo = createSafeElement('span', 'Loading events...', '', { id: 'events-page-info' });

  const controls = createSafeElement('div', '', 'pagination-controls');
  const prevBtn = createSafeElement('button', 'Previous', 'btn btn-secondary btn-sm', {
    id: 'btn-events-prev',
    type: 'button',
    disabled: 'true'
  });
  prevBtn.innerHTML = `${getIcon('chevronLeft')} Previous`;
  prevBtn.addEventListener('click', () => {
    if (state.events.offset > 0) {
      state.events.offset = Math.max(0, state.events.offset - state.events.limit);
      loadEvents();
    }
  });

  const nextBtn = createSafeElement('button', 'Next', 'btn btn-secondary btn-sm', {
    id: 'btn-events-next',
    type: 'button',
    disabled: 'true'
  });
  nextBtn.innerHTML = `Next ${getIcon('chevronRight')}`;
  nextBtn.addEventListener('click', () => {
    if (state.events.offset + state.events.limit < state.events.total) {
      state.events.offset += state.events.limit;
      loadEvents();
    }
  });

  controls.append(prevBtn, nextBtn);
  paginationBar.append(pageInfo, controls);

  // Stream Storage Maintenance Strip (Separated from Primary Actions)
  const maintenanceBar = createSafeElement('div', '', 'events-maintenance-card', { id: 'events-maintenance-card' });

  const mInfo = createSafeElement('div', '', 'maintenance-info-group');
  const mIcon = createSafeElement('div', '', 'maintenance-icon');
  mIcon.innerHTML = getIcon('database');

  const mTextGroup = createSafeElement('div', '', 'maintenance-text-group');
  const mTitle = createSafeElement('div', 'Log Stream Storage', 'maintenance-title');
  const mCountDesc = createSafeElement('div', '', 'maintenance-subtitle', { id: 'maintenance-count-desc' });
  mCountDesc.innerHTML = `Loading stored event volume in <code class="code-pill">output/events.jsonl</code>...`;
  mTextGroup.append(mTitle, mCountDesc);
  mInfo.append(mIcon, mTextGroup);

  const mAction = createSafeElement('div', '', 'maintenance-action-group');
  const clearBtn = createSafeElement('button', 'Clear Stored Events', 'btn btn-danger btn-sm', {
    id: 'btn-open-clear-modal',
    type: 'button',
    title: 'Clear locally stored events stream'
  });
  clearBtn.innerHTML = `${getIcon('trash')} Clear Stored Events`;
  clearBtn.addEventListener('click', () => {
    openClearConfirmationModal();
  });
  mAction.appendChild(clearBtn);

  maintenanceBar.append(mInfo, mAction);

  container.append(header, bannerContainer, tableContainer, paginationBar, maintenanceBar);
}

export async function loadEvents() {
  const tbody = document.getElementById('events-table-tbody');
  const pageInfo = document.getElementById('events-page-info');
  const prevBtn = document.getElementById('btn-events-prev');
  const nextBtn = document.getElementById('btn-events-next');
  const refreshBtn = document.getElementById('btn-events-refresh');

  if (!tbody) return;

  state.events.loading = true;
  if (refreshBtn) {
    refreshBtn.disabled = true;
  }

  // Render Skeleton Loading Rows
  tbody.innerHTML = '';
  for (let i = 0; i < 5; i++) {
    const tr = createSafeElement('tr');
    tr.innerHTML = `
      <td><div class="skeleton" style="height: 16px; width: 85px;"></div></td>
      <td><div class="skeleton" style="height: 16px; width: 70px;"></div></td>
      <td><div class="skeleton" style="height: 16px; width: 90px;"></div></td>
      <td><div class="skeleton" style="height: 16px; width: 65px; border-radius: 99px;"></div></td>
      <td><div class="skeleton" style="height: 16px; width: 95px;"></div></td>
      <td><div class="skeleton" style="height: 16px; width: 95px;"></div></td>
      <td><div class="skeleton" style="height: 16px; width: 60px;"></div></td>
      <td><div class="skeleton" style="height: 16px; width: 110px;"></div></td>
      <td><div class="skeleton" style="height: 24px; width: 60px; border-radius: 4px;"></div></td>
    `;
    tbody.appendChild(tr);
  }

  try {
    const res = await api.events(state.events.limit, state.events.offset, state.events.status);
    const records = res.records || [];
    const total = res.total || 0;

    state.events.records = records;
    state.events.total = total;
    state.events.lastRefreshed = new Date();

    renderEventsRows(tbody, records);
    updatePagination(pageInfo, prevBtn, nextBtn, records.length, total);
    updateMaintenanceBar(total);
  } catch (err) {
    console.error('Failed to load events:', err);
    tbody.innerHTML = '';
    const errTr = createSafeElement('tr');
    const errTd = createSafeElement('td', '', '', { colspan: '9', style: 'text-align: center; padding: 30px; color: var(--color-status-error);' });
    errTd.innerHTML = `${getIcon('warning')} <strong>Failed to load events:</strong> ${err.message || 'Check backend connection.'}`;
    errTr.appendChild(errTd);
    tbody.appendChild(errTr);

    if (pageInfo) pageInfo.textContent = 'Error loading events';
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    updateMaintenanceBar(0);
  } finally {
    state.events.loading = false;
    if (refreshBtn) {
      refreshBtn.disabled = false;
    }
  }
}

function updateMaintenanceBar(total) {
  const mCountDesc = document.getElementById('maintenance-count-desc');
  const clearBtn = document.getElementById('btn-open-clear-modal');

  if (mCountDesc) {
    if (total === 0) {
      mCountDesc.innerHTML = `<span><strong>0</strong> stored events in <code class="code-pill">output/events.jsonl</code> (Stream is empty)</span>`;
    } else {
      mCountDesc.innerHTML = `<span><strong>${total.toLocaleString()}</strong> stored events in <code class="code-pill">output/events.jsonl</code></span>`;
    }
  }

  if (clearBtn) {
    clearBtn.disabled = total === 0;
    clearBtn.title = total === 0 ? 'No stored events to clear' : `Clear all ${total.toLocaleString()} stored events`;
  }
}

function openClearConfirmationModal() {
  const modalBackdrop = document.getElementById('clear-events-modal-backdrop');
  const modalContent = document.getElementById('clear-events-modal-content');
  if (!modalBackdrop || !modalContent) return;

  const total = state.events.total || 0;
  if (total === 0) return;

  modalContent.innerHTML = '';

  // Header
  const header = createSafeElement('div', '', 'modal-header');
  const titleGroup = createSafeElement('div', '', 'modal-title-group');
  const h3 = createSafeElement('h3', 'Clear Stored Events Stream', '', { id: 'clear-events-modal-title' });
  h3.style.color = 'var(--palette-crimson-rose)';
  const summaryLine = createSafeElement('div', 'Irreversible Local Storage Cleanup', 'modal-summary-line');
  titleGroup.append(h3, summaryLine);

  const closeBtn = createSafeElement('button', '', 'btn btn-ghost btn-sm modal-close-btn', {
    'aria-label': 'Close modal',
    style: 'padding: 6px;'
  });
  closeBtn.innerHTML = getIcon('close');
  closeBtn.addEventListener('click', closeClearConfirmationModal);
  header.append(titleGroup, closeBtn);

  // Body
  const body = createSafeElement('div', '', 'modal-body');

  // Danger Alert Box
  const dangerBox = createSafeElement('div', '', 'error-alert-box', { style: 'margin-bottom: 18px;' });
  const dangerTitle = createSafeElement('div', '', 'error-alert-title');
  dangerTitle.innerHTML = `${getIcon('warning')} Permanent Deletion Warning`;
  const dangerDesc = createSafeElement('p', '', '', { style: 'font-size: 0.86rem; color: #ffb3c0; margin: 4px 0 0 0; line-height: 1.55;' });
  dangerDesc.innerHTML = `This operation will permanently purge all <strong>${total.toLocaleString()}</strong> events from your local LogForge event stream (<code>output/events.jsonl</code>).`;
  dangerBox.append(dangerTitle, dangerDesc);

  // Explanation notes
  const explainList = createSafeElement('ul', '', 'danger-modal-list', {
    style: 'margin-bottom: 20px; padding-left: 20px; font-size: 0.84rem; color: var(--palette-soft-blush); line-height: 1.7;'
  });
  explainList.innerHTML = `
    <li>All forensic event records, SHA-256 lineage proofs, and unmapped fields will be deleted.</li>
    <li>Events Explorer and all operational dashboard metrics will reset to 0.</li>
    <li>This action cannot be undone. New logs can be ingested at any time via the Interactive Normalizer or Batch Ingest.</li>
  `;

  // Accidental activation prevention checkbox
  const checkWrapper = createSafeElement('div', '', 'danger-confirm-check-wrapper');
  const checkbox = createSafeElement('input', '', '', {
    type: 'checkbox',
    id: 'confirm-clear-events-checkbox'
  });
  const checkLabel = createSafeElement('label', '', 'danger-confirm-label', {
    for: 'confirm-clear-events-checkbox'
  });
  checkLabel.innerHTML = `<span>I understand that this action is permanent and will delete all <strong>${total.toLocaleString()}</strong> stored events.</span>`;
  checkWrapper.append(checkbox, checkLabel);

  body.append(dangerBox, explainList, checkWrapper);

  // Footer
  const footer = createSafeElement('div', '', 'modal-footer');
  const cancelBtn = createSafeElement('button', 'Cancel', 'btn btn-secondary', { type: 'button' });
  cancelBtn.addEventListener('click', closeClearConfirmationModal);

  const confirmBtn = createSafeElement('button', '', 'btn btn-danger', {
    type: 'button',
    disabled: 'true',
    id: 'btn-confirm-execute-clear'
  });
  confirmBtn.innerHTML = `${getIcon('trash')} Clear ${total.toLocaleString()} Events`;

  // Prevent accidental activation: only enabled when checkbox is checked
  checkbox.addEventListener('change', () => {
    confirmBtn.disabled = !checkbox.checked;
  });

  confirmBtn.addEventListener('click', async () => {
    confirmBtn.disabled = true;
    cancelBtn.disabled = true;
    confirmBtn.innerHTML = `<span class="skeleton" style="display:inline-block; width:14px; height:14px; border-radius:50%; margin-right:8px;"></span> Clearing Events...`;

    try {
      const res = await api.clearEvents();
      closeClearConfirmationModal();
      showEventsBanner('success', `Successfully cleared ${res.deleted_count ?? total} events from output/events.jsonl.`);
      announceAria(`Cleared ${res.deleted_count ?? total} events from local storage.`);

      // Smooth scroll workspace to top to show banner and refreshed empty state
      const workspace = document.querySelector('.workspace');
      if (workspace) {
        workspace.scrollTo({ top: 0, behavior: 'smooth' });
      }

      // Reset to first page & refresh explorer table
      state.events.offset = 0;
      await loadEvents();

      // Refresh related dashboard metrics
      await loadDashboardData();
    } catch (err) {
      console.error('Failed to clear events:', err);
      closeClearConfirmationModal();
      showEventsBanner('error', `Failed to clear events: ${err.message || 'Server error'}`);
    }
  });

  footer.append(cancelBtn, confirmBtn);

  modalContent.append(header, body, footer);
  modalBackdrop.classList.add('open');
  document.body.style.overflow = 'hidden';
  cancelBtn.focus();
}

function closeClearConfirmationModal() {
  const modalBackdrop = document.getElementById('clear-events-modal-backdrop');
  if (modalBackdrop) {
    modalBackdrop.classList.remove('open');
    document.body.style.overflow = '';
    const openBtn = document.getElementById('btn-open-clear-modal');
    if (openBtn) {
      openBtn.focus();
    }
  }
}

function showEventsBanner(type, message) {
  const container = document.getElementById('events-banner-container');
  if (!container) return;

  container.innerHTML = '';
  const isSuccess = type === 'success';

  const banner = createSafeElement('div', '', isSuccess ? 'events-alert-banner banner-success' : 'events-alert-banner banner-error');
  const textSpan = createSafeElement('span', '', '');
  textSpan.innerHTML = `${getIcon(isSuccess ? 'check' : 'warning')} <span>${message}</span>`;

  const dismissBtn = createSafeElement('button', '', 'btn-banner-dismiss', {
    'aria-label': 'Dismiss notification',
    type: 'button'
  });
  dismissBtn.innerHTML = getIcon('close');
  dismissBtn.addEventListener('click', () => {
    banner.remove();
  });

  banner.append(textSpan, dismissBtn);
  container.appendChild(banner);

  // Auto-dismiss success after 6 seconds
  if (isSuccess) {
    setTimeout(() => {
      banner.style.opacity = '0';
      setTimeout(() => banner.remove(), 240);
    }, 6000);
  }
}

function renderEventsRows(tbody, records) {
  tbody.innerHTML = '';

  if (records.length === 0) {
    const tr = createSafeElement('tr');
    const td = createSafeElement('td', '', '', { colspan: '9', style: 'text-align: center; padding: 40px; color: var(--color-text-muted);' });
    const emptyIcon = createSafeElement('div', '', '', { style: 'margin-bottom: 8px;' });
    emptyIcon.innerHTML = getIcon('events');
    const text = createSafeElement('div', state.events.status
      ? `No stored events found with status "${state.events.status}".`
      : 'No events stored in output/events.jsonl yet. Use the Interactive Normalizer or Batch Ingest to process events.');
    td.append(emptyIcon, text);
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  records.forEach(r => {
    const meta = r.ulpf_metadata || {};
    const ocsf = r.ocsf_event || {};
    const status = meta.parse_status || 'unknown';

    const tr = createSafeElement('tr');

    // UUID (Truncated)
    const tdId = createSafeElement('td', '', 'mono');
    const fullId = meta.raw_event_id || '—';
    const shortId = fullId.length > 10 ? fullId.substring(0, 8) + '...' : fullId;
    const spanId = createSafeElement('span', shortId, '', { title: fullId });
    tdId.appendChild(spanId);

    // Parser Extension
    const tdExt = createSafeElement('td', meta.extension_id || '—');

    // Mapping Profile
    const tdProfile = createSafeElement('td', meta.mapping_profile_id || '—', 'mono');

    // Status Badge
    const tdStatus = createSafeElement('td');
    const badge = createSafeElement('span', '', `status-badge badge-${status}`);
    const iconName = status === 'success' ? 'success' : status === 'partial' ? 'warning' : 'failed';
    badge.innerHTML = `${getIcon(iconName)} ${status}`;
    tdStatus.appendChild(badge);

    // Source IP
    const srcIp = ocsf.src_endpoint?.ip || '—';
    const tdSrc = createSafeElement('td', srcIp, 'mono');

    // Dest IP
    const dstIp = ocsf.dst_endpoint?.ip || '—';
    const tdDst = createSafeElement('td', dstIp, 'mono');

    // Action / Activity
    const action = ocsf.action || ocsf.activity_name || '—';
    const tdAction = createSafeElement('td', action);

    // Timestamp
    const timeStr = formatTimestamp(ocsf.time, ocsf.metadata?.original_time);
    const tdTime = createSafeElement('td', timeStr, 'mono', { style: 'font-size: 0.78rem;' });

    // Inspect Action Button
    const tdInspect = createSafeElement('td');
    const inspectBtn = createSafeElement('button', 'Inspect', 'btn btn-secondary btn-sm', {
      type: 'button',
      'aria-label': `Inspect event ${fullId}`
    });
    inspectBtn.innerHTML = `${getIcon('inspect')} Inspect`;
    inspectBtn.addEventListener('click', () => {
      openInspector(fullId, inspectBtn, r);
    });
    tdInspect.appendChild(inspectBtn);

    tr.append(tdId, tdExt, tdProfile, tdStatus, tdSrc, tdDst, tdAction, tdTime, tdInspect);
    tbody.appendChild(tr);
  });
}

function updatePagination(pageInfo, prevBtn, nextBtn, pageCount, total) {
  const start = total === 0 ? 0 : state.events.offset + 1;
  const end = Math.min(state.events.offset + pageCount, total);

  if (pageInfo) {
    pageInfo.textContent = `Showing ${start}–${end} of ${total} events`;
  }

  if (prevBtn) {
    prevBtn.disabled = state.events.offset <= 0;
  }

  if (nextBtn) {
    nextBtn.disabled = state.events.offset + state.events.limit >= total;
  }
}
