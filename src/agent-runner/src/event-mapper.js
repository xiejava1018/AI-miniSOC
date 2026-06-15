/**
 * Event mapper: converts pi-agent-core events to JSON-RPC event format
 * Maps native pi-agent-core event types to SSE-friendly JSON-RPC events
 */

import { writeEvent, writeErrorEvent } from './rpc-protocol.js';

/**
 * Map pi-agent-core event types to JSON-RPC event types
 */
const EVENT_TYPE_MAP = {
  // Text streaming events
  text_delta: 'text_delta',
  text_done: 'text_done',

  // Tool execution events
  tool_execution_start: 'tool_execution_start',
  tool_execution_end: 'tool_execution_end',
  tool_execution_error: 'tool_execution_error',

  // Message/turn events
  message_end: 'message_end',
  turn_end: 'turn_end',

  // Session events
  agent_end: 'agent_end',
  agent_error: 'error',
  error: 'error',

  // Usage events
  usage: 'usage',

  // Trace events
  trace_llm: 'trace.llm',
  trace_tool: 'trace.tool'
};

/**
 * Create an event handler for a specific session
 * @param {string} sessionId - Session ID
 * @param {string} traceId - Trace ID for this request
 * @param {AbortController} abortController - Abort controller for cancellation
 * @returns {function} Event handler function
 */
export function createEventHandler(sessionId, traceId, abortController = null) {
  return (event) => {
    const timestamp = Date.now();

    // Handle text_delta events (most common streaming event)
    if (event.type === 'message_update') {
      const msgEvent = event.assistantMessageEvent;
      if (msgEvent?.type === 'text_delta') {
        writeEvent('agent.event', {
          type: 'text_delta',
          delta: msgEvent.delta,
          sessionId,
          ts: timestamp,
          trace_id: traceId
        });
        return;
      }

      // Handle other message update subtypes
      if (msgEvent?.type === 'text_done') {
        writeEvent('agent.event', {
          type: 'text_done',
          text: msgEvent.text || '',
          sessionId,
          ts: timestamp,
          trace_id: traceId
        });
        return;
      }

      // Handle tool call events
      if (msgEvent?.type === 'tool_call') {
        writeEvent('agent.event', {
          type: 'tool_call',
          tool: msgEvent.tool,
          arguments: msgEvent.arguments,
          sessionId,
          ts: timestamp,
          trace_id: traceId
        });
        return;
      }

      if (msgEvent?.type === 'tool_result') {
        writeEvent('agent.event', {
          type: 'tool_result',
          tool: msgEvent.tool,
          result: msgEvent.result,
          sessionId,
          ts: timestamp,
          trace_id: traceId
        });
        return;
      }
    }

    // Handle tool execution start
    if (event.type === 'tool_execution_start') {
      writeEvent('agent.event', {
        type: 'tool_execution_start',
        tool: event.tool,
        arguments: event.arguments,
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    // Handle tool execution end
    if (event.type === 'tool_execution_end') {
      writeEvent('agent.event', {
        type: 'tool_execution_end',
        tool: event.tool,
        status: event.status,
        result: event.result,
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    // Handle tool execution error
    if (event.type === 'tool_execution_error') {
      writeEvent('agent.event', {
        type: 'tool_execution_error',
        tool: event.tool,
        error: event.error,
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    // Handle message end
    if (event.type === 'message_end') {
      writeEvent('agent.event', {
        type: 'message_end',
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    // Handle turn end
    if (event.type === 'turn_end') {
      writeEvent('agent.event', {
        type: 'turn_end',
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    // Handle agent end (final event)
    if (event.type === 'agent_end') {
      writeEvent('agent.event', {
        type: 'agent_end',
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    // Handle errors
    if (event.type === 'error' || event.type === 'agent_error') {
      writeErrorEvent(sessionId, event.error || event.message, traceId);
      return;
    }

    // Handle usage events (for metrics)
    if (event.type === 'usage') {
      writeEvent('agent.event', {
        type: 'usage',
        inputTokens: event.inputTokens,
        outputTokens: event.outputTokens,
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    // Handle trace events
    if (event.type === 'trace_llm') {
      writeEvent('agent.event', {
        type: 'trace.llm',
        ...event,
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    if (event.type === 'trace_tool') {
      writeEvent('agent.event', {
        type: 'trace.tool',
        ...event,
        sessionId,
        ts: timestamp,
        trace_id: traceId
      });
      return;
    }

    // Unknown event type - log and ignore (don't crash)
    // In production, this could be sent to a debug log
    if (process.env.DEBUG) {
      console.error(`[pi-agent-runner] Unknown event type: ${event.type}`, JSON.stringify(event));
    }
  };
}

/**
 * Get display name for event type
 * @param {string} eventType - Original event type
 * @returns {string} Mapped event type
 */
export function mapEventType(eventType) {
  return EVENT_TYPE_MAP[eventType] || eventType;
}