// LogForge Extensions Registry Module
// Read-only catalog of modular parser extensions discovered dynamically from config/extensions.yaml

import { api } from '../api.js';
import { state, createSafeElement } from '../state.js';
import { icons, getIcon } from '../icons.js';
import { setSourceHint } from './normalizer.js';

export function initExtensions() {
  const container = document.getElementById('tab-extensions');
  if (!container) return;

  renderExtensionsShell(container);
  loadExtensionsCatalog();
}

function renderExtensionsShell(container) {
  container.innerHTML = '';

  // Header
  const header = createSafeElement('div', '', 'section-header');
  const titleGroup = createSafeElement('div', '', 'section-title-group');
  const title = createSafeElement('h2', '');
  title.innerHTML = `${getIcon('extensions')} Extensions Registry`;
  const desc = createSafeElement('p', 'Plug-and-play parser extensions loaded dynamically from configuration. Zero core code modifications required for new log formats.', 'section-description');
  titleGroup.append(title, desc);

  const actions = createSafeElement('div', '', 'section-actions');
  const readOnlyBadge = createSafeElement('span', 'Read-Only Catalog', 'status-badge badge-info');
  actions.appendChild(readOnlyBadge);

  header.append(titleGroup, actions);

  // Architecture Callout Card
  const callout = createSafeElement('div', '', 'glass-card', {
    style: 'display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; margin-bottom: 24px; flex-wrap: wrap; gap: 10px;'
  });
  const calloutText = createSafeElement('div', '', '', { style: 'display: flex; align-items: center; gap: 10px; font-size: 0.88rem;' });
  calloutText.innerHTML = `${getIcon('info')} <span><strong>Decoupled Architecture:</strong> LogForge routes formats via deterministic scoring & heuristics directly into registered extension parsers.</span>`;

  const totalLoaded = createSafeElement('div', 'Loading catalog...', 'ocsf-badge', { id: 'ext-total-count' });
  callout.append(calloutText, totalLoaded);

  // Extensions Grid
  const grid = createSafeElement('div', '', 'extensions-grid', { id: 'extensions-cards-grid' });

  container.append(header, callout, grid);
}

export async function loadExtensionsCatalog() {
  const grid = document.getElementById('extensions-cards-grid');
  const countBadge = document.getElementById('ext-total-count');
  if (!grid) return;

  // Render skeleton cards while loading
  grid.innerHTML = '';
  for (let i = 0; i < 5; i++) {
    const card = createSafeElement('div', '', 'extension-card');
    card.innerHTML = `
      <div class="skeleton" style="height: 24px; width: 60%; margin-bottom: 12px;"></div>
      <div class="skeleton" style="height: 40px; width: 100%; margin-bottom: 16px;"></div>
      <div class="skeleton" style="height: 70px; width: 100%; margin-bottom: 16px;"></div>
      <div class="skeleton" style="height: 32px; width: 100%;"></div>
    `;
    grid.appendChild(card);
  }

  try {
    const res = await api.extensions();
    const extensions = res.extensions || [];
    state.extensions = extensions;

    if (countBadge) {
      countBadge.textContent = `${extensions.length} Active Extensions`;
    }

    renderExtensionCards(grid, extensions);
  } catch (err) {
    console.error('Failed to load extensions:', err);
    grid.innerHTML = `<div class="error-alert-box" style="grid-column: 1 / -1;">
      <div class="error-alert-title">${getIcon('warning')} Unable to load extensions catalog</div>
      <p style="color: var(--jewel-error); font-size: 0.86rem;">${err.message}</p>
    </div>`;
  }
}

function renderExtensionCards(grid, extensions) {
  grid.innerHTML = '';

  if (extensions.length === 0) {
    grid.innerHTML = `<p class="section-description" style="grid-column: 1 / -1; text-align: center; padding: 40px;">
      No parser extensions registered in config/extensions.yaml.
    </p>`;
    return;
  }

  extensions.forEach(ext => {
    const card = createSafeElement('div', '', 'extension-card');

    // Header with Extension ID & Version
    const cardHeader = createSafeElement('div', '', 'ext-card-header');
    const titleSpan = createSafeElement('span', ext.extension_id, 'ext-id-title');
    const versionBadge = createSafeElement('span', `v${ext.extension_version || '1.0.0'}`, 'status-badge badge-info', {
      style: 'font-family: var(--font-mono);'
    });
    cardHeader.append(titleSpan, versionBadge);

    // Description
    const desc = createSafeElement('p', ext.description || 'Parser extension component', 'ext-desc');

    // Metadata Grid
    const metaGrid = createSafeElement('div', '', 'ext-meta-grid');
    const items = [
      { k: 'Format Family', v: ext.format_id || '—' },
      { k: 'Vendor', v: ext.vendor || 'Generic' },
      { k: 'Product', v: ext.product || '—' },
      { k: 'Default Profile', v: ext.default_mapping_profile || '—' }
    ];

    items.forEach(it => {
      const row = createSafeElement('div');
      row.innerHTML = `<span style="color: var(--ink-muted);">${it.k}:</span> <strong style="color: var(--ink-title);">${it.v}</strong>`;
      metaGrid.appendChild(row);
    });

    // Action Button ("Use as Source Hint")
    const btn = createSafeElement('button', 'Use as Source Hint', 'btn btn-secondary btn-sm', {
      type: 'button',
      style: 'width: 100%; justify-content: center; margin-top: auto;'
    });
    btn.innerHTML = `${getIcon('arrowRight')} Use as Source Hint`;
    btn.addEventListener('click', () => {
      setSourceHint(ext.extension_id);
      // Switch to normalizer tab
      document.querySelector('.tab-button[data-tab="normalizer"]')?.click();
    });

    card.append(cardHeader, desc, metaGrid, btn);
    grid.appendChild(card);
  });
}
