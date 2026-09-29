// LogForge Main Application Entry Point
// Orchestrates vertical sidebar rail navigation, health probing, state management, and module initialization

import { api } from './api.js';
import { state, announceAria } from './state.js';
import { icons, getIcon } from './icons.js';

import { initNormalizer, updateSourceHintOptions } from './modules/normalizer.js';
import { initDashboard, loadDashboardData } from './modules/dashboard.js?v=1.8.0';
import { initBatch } from './modules/batch.js';
import { initEventsExplorer, loadEvents } from './modules/events.js';
import { initInspector } from './modules/inspector.js';
import { initExtensions, loadExtensionsCatalog } from './modules/extensions.js';
import { initAiOnboarding } from './modules/ai-onboarding.js';

document.addEventListener('DOMContentLoaded', () => {
  setupNavigation();
  initInspector();
  initNormalizer();
  initDashboard();
  initBatch();
  initEventsExplorer();
  initExtensions();
  initAiOnboarding();

  // Initial probe and extensions discovery
  checkHealth();
  discoverExtensions();

  // 60-second background health heartbeat
  setInterval(checkHealth, 60000);
});

function setupNavigation() {
  const tabButtons = document.querySelectorAll('.rail-tab-btn[data-tab]');

  // Insert SVGs into sidebar navigation buttons
  tabButtons.forEach(btn => {
    const tabId = btn.getAttribute('data-tab');
    const iconContainer = btn.querySelector('.rail-tab-icon');
    if (iconContainer && icons[tabId]) {
      iconContainer.innerHTML = getIcon(tabId);
    }

    btn.addEventListener('click', () => {
      switchTab(tabId);
    });
  });

  // Insert bottom sidebar icons
  const settingsIcon = document.getElementById('rail-settings-icon');
  if (settingsIcon) settingsIcon.innerHTML = getIcon('settings');

  const refreshIcon = document.getElementById('rail-refresh-icon');
  if (refreshIcon) refreshIcon.innerHTML = getIcon('refresh');

  // Insert search icon in header
  const searchIcon = document.querySelector('.header-search-icon');
  if (searchIcon) searchIcon.innerHTML = getIcon('search');

  // Global Refresh Button
  const refreshAllBtn = document.getElementById('rail-refresh-all-btn');
  if (refreshAllBtn) {
    refreshAllBtn.addEventListener('click', () => {
      refreshIcon?.classList.add('rotating');
      Promise.all([checkHealth(), discoverExtensions(), refreshCurrentTab()]).finally(() => {
        setTimeout(() => refreshIcon?.classList.remove('rotating'), 600);
      });
    });
  }

  // Quick Search Bar in Header
  const searchInput = document.getElementById('header-quick-search');
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && searchInput.value.trim().length > 0) {
        switchTab('events');
      }
    });
  }
}

function refreshCurrentTab() {
  if (state.activeTab === 'dashboard') {
    return loadDashboardData();
  } else if (state.activeTab === 'events') {
    return loadEvents();
  } else if (state.activeTab === 'extensions') {
    return loadExtensionsCatalog();
  }
  return Promise.resolve();
}

export function switchTab(tabId) {
  const tabButtons = document.querySelectorAll('.rail-tab-btn[data-tab]');
  const tabPanels = document.querySelectorAll('.tab-panel');

  tabButtons.forEach(btn => {
    const isTarget = btn.getAttribute('data-tab') === tabId;
    btn.classList.toggle('active', isTarget);
    btn.setAttribute('aria-selected', isTarget ? 'true' : 'false');
  });

  tabPanels.forEach(panel => {
    const isTarget = panel.id === `tab-${tabId}`;
    panel.classList.toggle('active', isTarget);
  });

  state.activeTab = tabId;
  announceAria(`Navigated to ${tabId} view`);

  // Refresh tab-specific views on switch
  if (tabId === 'dashboard') {
    loadDashboardData();
  } else if (tabId === 'events') {
    loadEvents();
  } else if (tabId === 'extensions') {
    loadExtensionsCatalog();
  } else if (tabId === 'normalizer') {
    updateSourceHintOptions();
  }
}

async function checkHealth() {
  const dot = document.getElementById('health-indicator-dot');
  const label = document.getElementById('health-status-label');
  const versions = document.getElementById('health-versions-summary');
  const railSettingsDot = document.getElementById('rail-settings-icon');

  try {
    const health = await api.health();
    state.backendOnline = true;
    state.healthData = health;

    if (dot) dot.className = 'health-dot online';
    if (label) label.textContent = 'Engine Online';
    if (versions) versions.textContent = `v${health.version || '1.0.0'} • OCSF ${health.ocsf_version || '1.4.0'}`;
    if (railSettingsDot) railSettingsDot.style.color = 'var(--jewel-success-bright)';
  } catch (err) {
    console.warn('Backend health check failed:', err);
    state.backendOnline = false;
    state.healthData = null;

    if (dot) dot.className = 'health-dot';
    if (label) label.textContent = 'Backend Offline';
    if (versions) versions.textContent = 'Disconnected';
    if (railSettingsDot) railSettingsDot.style.color = 'var(--jewel-error-bright)';
  }
}

async function discoverExtensions() {
  try {
    const res = await api.extensions();
    state.extensions = res.extensions || [];
    updateSourceHintOptions();
  } catch (err) {
    console.warn('Initial extensions discovery failed:', err);
  }
}
