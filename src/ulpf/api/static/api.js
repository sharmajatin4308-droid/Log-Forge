// LogForge Centralized API Client Module
// Implements exact routes, timeouts, error normalization, and abort control per frontend.md §17

export class ApiError extends Error {
  constructor(status, message, detail = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

const API_BASE = ''; // Same-origin relative path

async function apiRequest(method, path, body = null, options = {}) {
  const { timeout = 30000, signal: externalSignal } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  // Link external abort signal if provided
  if (externalSignal) {
    externalSignal.addEventListener('abort', () => controller.abort());
  }

  try {
    const fetchOptions = {
      method,
      headers: {
        'Accept': 'application/json'
      },
      signal: controller.signal
    };

    if (body !== null) {
      fetchOptions.headers['Content-Type'] = 'application/json';
      fetchOptions.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE}${path}`, fetchOptions);

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      const message = errorBody.detail || `HTTP Error ${response.status}`;
      throw new ApiError(response.status, message, errorBody);
    }

    return await response.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      if (externalSignal?.aborted) {
        throw new ApiError(0, 'Request cancelled by user');
      }
      throw new ApiError(0, `Request timed out after ${timeout / 1000}s`);
    }
    if (err instanceof ApiError) throw err;
    throw new ApiError(0, `Network error: ${err.message || 'Unable to connect to backend server'}`);
  } finally {
    clearTimeout(timeoutId);
  }
}

export const api = {
  /**
   * Health probe and version check
   * @returns {Promise<{status: string, version: string, ocsf_version: string}>}
   */
  health() {
    return apiRequest('GET', '/api/health', null, { timeout: 5000 });
  },

  /**
   * Lists loaded parser extensions
   * @returns {Promise<{extensions: Array}>}
   */
  extensions() {
    return apiRequest('GET', '/api/extensions', null, { timeout: 10000 });
  },

  /**
   * Ingest and normalize a single raw log string
   * @param {string} payload
   * @param {string|null} sourceHint
   * @returns {Promise<object>} ULPFRecord
   */
  ingest(payload, sourceHint = null) {
    return apiRequest('POST', '/api/ingest', {
      payload,
      source_hint: sourceHint || null
    }, { timeout: 30000 });
  },

  /**
   * Ingest a batch of log lines (maximum 100 events)
   * @param {string[]} events
   * @param {AbortSignal} [signal]
   * @returns {Promise<{records: Array, stats: {total: number, success: number, partial: number, failed: number, total_duration_ms: number}}>}
   */
  ingestBatch(events, signal = null) {
    if (events.length > 100) {
      throw new ApiError(400, 'Maximum 100 events per batch request');
    }
    return apiRequest('POST', '/api/ingest/batch', { events }, { timeout: 60000, signal });
  },

  /**
   * Fetch stored events with pagination and optional status filter
   * @param {number} limit (1-500, default 25)
   * @param {number} offset (default 0)
   * @param {string|null} status ('success' | 'partial' | 'failed')
   * @returns {Promise<{records: Array, total: number}>}
   */
  events(limit = 25, offset = 0, status = null) {
    let path = `/api/events?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`;
    // Backend strictly regex-validates: ^(success|partial|failed)$
    if (status && ['success', 'partial', 'failed'].includes(status)) {
      path += `&status=${encodeURIComponent(status)}`;
    }
    return apiRequest('GET', path, null, { timeout: 30000 });
  },

  /**
   * Retrieve a single processed event by its UUID
   * @param {string} rawEventId
   * @returns {Promise<object>} ULPFRecord
   */
  event(rawEventId) {
    if (!rawEventId) {
      throw new ApiError(400, 'Invalid raw_event_id');
    }
    return apiRequest('GET', `/api/events/${encodeURIComponent(rawEventId)}`, null, { timeout: 15000 });
  },

  /**
   * Clears all stored events from the local JSONL output stream (destructive action)
   * @returns {Promise<{status: string, deleted_count: number}>}
   */
  clearEvents() {
    return apiRequest('DELETE', '/api/events', null, { timeout: 15000 });
  }
};
