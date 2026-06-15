/**
 * JSON-RPC protocol utilities for pi-agent-runner
 * Handles encoding/decoding of JSON-RPC messages over stdio
 */

/**
 * Write a JSON-RPC response to stdout
 * @param {object} res - Response object
 * @param {string|number|null} res.id - Request ID (null for notifications)
 * @param {object} res.result - Result data (if success)
 * @param {object} res.error - Error object (if failure)
 */
export function writeResponse(res) {
  const line = JSON.stringify(res);
  process.stdout.write(line + '\n');
}

/**
 * Write a JSON-RPC error response
 * @param {string|number|null} id - Request ID
 * @param {number} code - Error code
 * @param {string} message - Error message
 * @param {object} [data] - Optional additional data
 */
export function writeError(id, code, message, data = null) {
  writeResponse({
    id,
    error: {
      code,
      message,
      ...(data && { data })
    }
  });
}

/**
 * Write a JSON-RPC event notification (id = "evt")
 * @param {string} method - Event method name
 * @param {object} params - Event parameters
 */
export function writeEvent(method, params) {
  writeResponse({
    id: 'evt',
    method,
    params
  });
}

/**
 * Write an error event notification
 * @param {string} sessionId - Session ID
 * @param {string} error - Error message
 * @param {string} [traceId] - Trace ID
 */
export function writeErrorEvent(sessionId, error, traceId = null) {
  writeEvent('agent.event', {
    type: 'error',
    error,
    sessionId,
    ts: Date.now(),
    ...(traceId && { trace_id: traceId })
  });
}

/**
 * JSON-RPC error codes
 */
export const ErrorCodes = {
  PARSE_ERROR: -32700,
  INVALID_REQUEST: -32600,
  METHOD_NOT_FOUND: -32601,
  INVALID_PARAMS: -32602,
  INTERNAL_ERROR: -32603
};

/**
 * Parse a JSON-RPC request from raw string
 * @param {string} raw - Raw input string
 * @returns {{ request: object|null, error: string|null }}
 */
export function parseRequest(raw) {
  try {
    const request = JSON.parse(raw);

    // Validate basic structure
    if (!request || typeof request !== 'object') {
      return { request: null, error: 'Invalid JSON object' };
    }

    if (!request.method || typeof request.method !== 'string') {
      return { request: null, error: 'Missing or invalid method' };
    }

    // params is optional, defaults to empty object
    if (!request.params) {
      request.params = {};
    }

    return { request, error: null };
  } catch (e) {
    return { request: null, error: `Parse error: ${e.message}` };
  }
}