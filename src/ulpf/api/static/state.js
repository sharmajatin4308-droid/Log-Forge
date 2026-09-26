// LogForge Centralized Application State & Utilities
// Follows frontend.md §16 specifications with explicit state boundaries

export const state = {
  // System
  backendOnline: false,
  healthData: null,
  activeTab: 'dashboard', // Default to Dashboard per target UI composition
  extensions: [],

  // Interactive Normalizer (P0 Core Demo)
  normalizer: {
    input: '',
    sourceHint: null,
    result: null,
    loading: false,
    error: null,
  },

  // Batch Ingest
  batch: {
    file: null,
    lines: [],
    chunks: [],
    currentChunk: 0,
    stats: { total: 0, success: 0, partial: 0, failed: 0, total_duration_ms: 0 },
    errors: [],
    processing: false,
    cancelled: false,
    startTime: null,
    wallClockDurationMs: 0,
    lastCompletedStats: null,
    abortController: null,
  },

  // Events Explorer
  events: {
    records: [],
    total: 0,
    offset: 0,
    limit: 25,
    status: null,
    loading: false,
    error: null,
    lastRefreshed: null,
  },

  // Dashboard
  dashboard: {
    metrics: null, // { total, success, partial, failed }
    recentEvents: [],
    loading: false,
    error: null,
    lastBatchEps: null, // Real batch EPS from current session
  },

  // Event Inspector Modal
  inspector: {
    record: null,
    isOpen: false,
    loading: false,
    error: null,
    triggerElement: null,
    advancedViewOpen: false,
  },
};

// Simple event listener registry for state changes
const listeners = new Map();

export function on(event, callback) {
  if (!listeners.has(event)) {
    listeners.set(event, new Set());
  }
  listeners.get(event).add(callback);
  return () => off(event, callback);
}

export function off(event, callback) {
  if (listeners.has(event)) {
    listeners.get(event).delete(callback);
  }
}

export function emit(event, data = null) {
  if (listeners.has(event)) {
    for (const callback of listeners.get(event)) {
      try {
        callback(data);
      } catch (err) {
        console.error(`Error in listener for ${event}:`, err);
      }
    }
  }
}

// -------------------------------------------------------------
// Security & Formatting Utilities (Mandatory Zero-innerHTML Policy)
// -------------------------------------------------------------

/**
 * Escapes characters for HTML output when text nodes are not directly usable.
 * NOTE: Always prefer element.textContent over innerHTML.
 */
export function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

/**
 * Creates an element with textContent (safe against XSS).
 */
export function createSafeElement(tag, text = '', classes = '', attributes = {}) {
  const el = document.createElement(tag);
  if (classes) {
    el.className = classes;
  }
  if (text !== null && text !== undefined) {
    el.textContent = String(text);
  }
  for (const [key, value] of Object.entries(attributes)) {
    if (value !== null && value !== undefined) {
      el.setAttribute(key, value);
    }
  }
  return el;
}

/**
 * Formats timestamps reliably. Handles Unix epoch ms, ISO strings, or raw strings.
 */
export function formatTimestamp(timeMs, rawOriginalTime = null) {
  if (timeMs && typeof timeMs === 'number' && timeMs > 0) {
    try {
      const date = new Date(timeMs);
      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3,
        hour12: false
      });
    } catch {
      // Fall through to raw original
    }
  }
  if (rawOriginalTime) {
    return String(rawOriginalTime);
  }
  return '—';
}

/**
 * Copies text safely to the clipboard with visual fallback.
 */
export async function copyToClipboard(text, triggerBtn = null) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      // Fallback using textarea
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      document.execCommand('copy');
      textArea.remove();
    }

    if (triggerBtn) {
      const originalText = triggerBtn.getAttribute('data-original-text') || triggerBtn.textContent;
      triggerBtn.setAttribute('data-original-text', originalText);
      triggerBtn.textContent = 'Copied!';
      triggerBtn.classList.add('btn-copied');
      setTimeout(() => {
        triggerBtn.textContent = originalText;
        triggerBtn.classList.remove('btn-copied');
      }, 1500);
    }
    announceAria('Copied to clipboard');
    return true;
  } catch (err) {
    console.warn('Clipboard copy failed:', err);
    if (triggerBtn) {
      triggerBtn.textContent = 'Failed';
      setTimeout(() => {
        triggerBtn.textContent = triggerBtn.getAttribute('data-original-text') || 'Copy';
      }, 1500);
    }
    return false;
  }
}

/**
 * Announces dynamic updates to screen readers via polite aria-live region.
 */
export function announceAria(message) {
  const liveRegion = document.getElementById('aria-announcer');
  if (liveRegion) {
    liveRegion.textContent = '';
    // Small timeout ensures screen readers detect text node insertion
    setTimeout(() => {
      liveRegion.textContent = message;
    }, 50);
  }
}
