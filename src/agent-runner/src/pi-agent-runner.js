/**
 * pi-agent-runner.js
 *
 * JSON-RPC stdio entry point for Pi Agent runtime.
 * Bridges FastAPI (Python) and pi-agent-core (Node.js).
 *
 * Protocol: Each line is a JSON message (\n delimited)
 * - Requests from FastAPI have "id" field
 * - Responses use same "id"
 * - Events use id="evt" (special case for streaming)
 */

import { Agent } from '@earendil-works/pi-agent-core';
import { getModel } from '@earendil-works/pi-ai';
import { randomUUID } from 'crypto';

import {
  writeResponse,
  writeError,
  writeEvent,
  ErrorCodes,
  parseRequest
} from './rpc-protocol.js';
import { createEventHandler } from './event-mapper.js';

// ============================================================================
// Global State
// ============================================================================

/** @type {Map<string, Agent>} Active agents by sessionId */
const agents = new Map();

/** @type {Map<string, AbortController>} Abort controllers by sessionId */
const abortControllers = new Map();

/** @type {Map<string, {sessionId: string, traceId: string}>} Pending requests */
const pendingRequests = new Map();

/** Configuration from environment */
const config = {
  defaultModel: process.env.PI_MODEL || 'openai/gpt-4o-mini',
  serviceToken: process.env.INTERNAL_SERVICE_TOKEN || '',
  baseUrl: process.env.PI_BASE_URL || null,  // For proxy/custom endpoints
  debug: process.env.DEBUG === 'true'
};

// ============================================================================
// Agent Management
// ============================================================================

/**
 * Get or create an Agent instance for a session
 * @param {string} sessionId - Session identifier
 * @param {string} model - Model identifier (provider/model-name)
 * @param {string} systemPrompt - Optional system prompt override
 * @returns {Agent} Agent instance
 */
function getOrCreateAgent(sessionId, model = null, systemPrompt = null) {
  if (!agents.has(sessionId)) {
    const modelConfig = parseModelConfig(model || config.defaultModel);

    const agent = new Agent({
      initialState: {
        systemPrompt: systemPrompt || 'You are a helpful SOC analyst assistant.',
        model: getModel(modelConfig.provider, modelConfig.model)
      },
      // POC phase: no tools, just verify LLM streaming
      tools: []
    });

    agents.set(sessionId, agent);
  }
  return agents.get(sessionId);
}

/**
 * Parse model string into provider and model name
 * @param {string} modelString - Model identifier (provider/model-name)
 * @returns {{provider: string, model: string}}
 */
function parseModelConfig(modelString) {
  const parts = modelString.split('/');
  if (parts.length === 2) {
    return { provider: parts[0], model: parts[1] };
  }
  // Default to openai if no provider specified
  return { provider: 'openai', model: modelString };
}

/**
 * Clean up agent resources for a session
 * @param {string} sessionId - Session identifier
 */
function cleanupAgent(sessionId) {
  agents.delete(sessionId);
  abortControllers.delete(sessionId);
}

// ============================================================================
// Request Handlers
// ============================================================================

/**
 * Handle agent.prompt request
 * Creates new agent session and streams response
 */
async function handlePrompt(request) {
  const { id, params } = request;
  const {
    sessionId,
    userMessage,
    model,
    skills = [],
    tools = [],
    systemPromptOverride = null,
    trace_id: traceId = null
  } = params;

  const trace = traceId || randomUUID();

  // Validate required params
  if (!sessionId || !userMessage) {
    writeError(id, ErrorCodes.INVALID_PARAMS, 'sessionId and userMessage are required');
    return;
  }

  try {
    // Get or create agent for this session
    const agent = getOrCreateAgent(sessionId, model, systemPromptOverride);

    // Create abort controller for this request
    const abortController = new AbortController();
    abortControllers.set(sessionId, abortController);

    // Create event handler
    const eventHandler = createEventHandler(sessionId, trace, abortController);
    agent.subscribe(eventHandler);

    // Send initial acknowledgment
    writeResponse({
      id,
      result: {
        ok: true,
        sessionId,
        trace_id: trace,
        status: 'streaming'
      }
    });

    // Send start event
    writeEvent('agent.event', {
      type: 'agent_start',
      sessionId,
      ts: Date.now(),
      trace_id: trace
    });

    // Execute prompt (stream response)
    try {
      const result = await agent.prompt(userMessage, {
        signal: abortController.signal,
        traceId: trace
      });

      // Send completion event
      writeEvent('agent.event', {
        type: 'agent_end',
        sessionId,
        ts: Date.now(),
        trace_id: trace,
        result: result
      });
    } catch (error) {
      // Handle abort
      if (error.name === 'AbortError') {
        writeEvent('agent.event', {
          type: 'agent_aborted',
          sessionId,
          ts: Date.now(),
          trace_id: trace
        });
      } else {
        // Handle other errors
        writeErrorEvent(sessionId, error.message, trace);
      }
    } finally {
      abortControllers.delete(sessionId);
    }

  } catch (error) {
    writeErrorEvent(sessionId, error.message, trace);
    writeResponse({
      id,
      result: {
        ok: false,
        sessionId,
        error: error.message
      }
    });
  }
}

/**
 * Handle agent.continue request
 * Continue existing session with new message
 */
async function handleContinue(request) {
  const { id, params } = request;
  const {
    sessionId,
    userMessage,
    model,
    trace_id: traceId = null
  } = params;

  const trace = traceId || randomUUID();

  if (!sessionId || !userMessage) {
    writeError(id, ErrorCodes.INVALID_PARAMS, 'sessionId and userMessage are required');
    return;
  }

  if (!agents.has(sessionId)) {
    writeError(id, ErrorCodes.INTERNAL_ERROR, `Session ${sessionId} not found. Use agent.prompt first.`);
    return;
  }

  try {
    const agent = agents.get(sessionId);
    const abortController = new AbortController();
    abortControllers.set(sessionId, abortController);

    const eventHandler = createEventHandler(sessionId, trace, abortController);
    agent.subscribe(eventHandler);

    writeResponse({
      id,
      result: {
        ok: true,
        sessionId,
        trace_id: trace,
        status: 'streaming'
      }
    });

    try {
      await agent.prompt(userMessage, { signal: abortController.signal, traceId: trace });
      writeEvent('agent.event', {
        type: 'agent_end',
        sessionId,
        ts: Date.now(),
        trace_id: trace
      });
    } catch (error) {
      if (error.name === 'AbortError') {
        writeEvent('agent.event', {
          type: 'agent_aborted',
          sessionId,
          ts: Date.now(),
          trace_id: trace
        });
      } else {
        writeErrorEvent(sessionId, error.message, trace);
      }
    } finally {
      abortControllers.delete(sessionId);
    }

  } catch (error) {
    writeErrorEvent(sessionId, error.message, trace);
    writeResponse({
      id,
      result: { ok: false, sessionId, error: error.message }
    });
  }
}

/**
 * Handle agent.abort request
 * Cancel running operation for a session
 */
function handleAbort(request) {
  const { id, params } = request;
  const { sessionId } = params;

  if (!sessionId) {
    writeError(id, ErrorCodes.INVALID_PARAMS, 'sessionId is required');
    return;
  }

  const abortController = abortControllers.get(sessionId);
  if (abortController) {
    abortController.abort();
    writeResponse({
      id,
      result: {
        ok: true,
        sessionId,
        message: 'Abort signal sent'
      }
    });
  } else {
    writeResponse({
      id,
      result: {
        ok: false,
        sessionId,
        message: 'No active operation to abort'
      }
    });
  }
}

/**
 * Handle agent.list_tools request
 * Return registered tools (POC: empty list)
 */
function handleListTools(request) {
  const { id } = request;

  writeResponse({
    id,
    result: {
      ok: true,
      tools: [],
      // POC: no tools implemented yet
      message: 'POC phase: tools not yet implemented'
    }
  });
}

/**
 * Handle agent.ping request
 * Simple health check
 */
function handlePing(request) {
  const { id } = request;

  writeResponse({
    id,
    result: {
      ok: true,
      status: 'pong',
      timestamp: Date.now(),
      version: '0.1.0-poc',
      activeSessions: agents.size
    }
  });
}

/**
 * Handle agent.reload_skills request
 * Hot reload skills (POC: placeholder)
 */
function handleReloadSkills(request) {
  const { id, params } = request;

  writeResponse({
    id,
    result: {
      ok: true,
      message: 'Skills reloaded',
      skills: []
    }
  });
}

/**
 * Handle agent.cleanup request
 * Remove agent for a session
 */
function handleCleanup(request) {
  const { id, params } = request;
  const { sessionId } = params;

  if (!sessionId) {
    writeError(id, ErrorCodes.INVALID_PARAMS, 'sessionId is required');
    return;
  }

  cleanupAgent(sessionId);
  writeResponse({
    id,
    result: {
      ok: true,
      sessionId,
      message: 'Session cleaned up'
    }
  });
}

// ============================================================================
// Method Router
// ============================================================================

const METHOD_HANDLERS = {
  'agent.prompt': handlePrompt,
  'agent.continue': handleContinue,
  'agent.abort': handleAbort,
  'agent.list_tools': handleListTools,
  'agent.ping': handlePing,
  'agent.reload_skills': handleReloadSkills,
  'agent.cleanup': handleCleanup
};

/**
 * Route request to appropriate handler
 * @param {object} request - Parsed JSON-RPC request
 */
async function routeRequest(request) {
  const { id, method } = request;

  const handler = METHOD_HANDLERS[method];
  if (!handler) {
    writeError(id, ErrorCodes.METHOD_NOT_FOUND, `Method not found: ${method}`);
    return;
  }

  try {
    await handler(request);
  } catch (error) {
    writeError(id, ErrorCodes.INTERNAL_ERROR, `Handler error: ${error.message}`);
    if (config.debug) {
      console.error('[pi-agent-runner] Handler error:', error);
    }
  }
}

// ============================================================================
// Main Loop
// ============================================================================

import * as readline from 'readline';

/**
 * Start the stdio JSON-RPC server
 */
function startServer() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
  });

  rl.on('line', async (line) => {
    // Skip empty lines
    const trimmed = line.trim();
    if (!trimmed) return;

    // Log raw input in debug mode
    if (config.debug) {
      console.error(`[pi-agent-runner] IN: ${trimmed}`);
    }

    // Parse request
    const { request, error: parseError } = parseRequest(trimmed);

    if (parseError) {
      writeError(null, ErrorCodes.PARSE_ERROR, parseError);
      return;
    }

    // Route to handler
    await routeRequest(request);
  });

  rl.on('close', () => {
    if (config.debug) {
      console.error('[pi-agent-runner] stdin closed, exiting...');
    }
    // Clean up all agents
    for (const sessionId of agents.keys()) {
      cleanupAgent(sessionId);
    }
    process.exit(0);
  });

  // Handle errors
  process.stdin.on('error', (error) => {
    console.error('[pi-agent-runner] stdin error:', error.message);
  });

  process.on('uncaughtException', (error) => {
    console.error('[pi-agent-runner] Uncaught exception:', error);
  });

  process.on('unhandledRejection', (reason) => {
    console.error('[pi-agent-runner] Unhandled rejection:', reason);
  });

  // Startup log
  console.error(`[pi-agent-runner] Started with model: ${config.defaultModel}`);
  console.error(`[pi-agent-runner] Debug mode: ${config.debug ? 'ON' : 'OFF'}`);

  // Send ready event
  writeEvent('agent.event', {
    type: 'runner_ready',
    ts: Date.now(),
    version: '0.1.0-poc',
    defaultModel: config.defaultModel
  });
}

// Start server
startServer();