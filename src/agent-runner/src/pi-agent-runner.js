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
import { getModel, registerApiProvider } from '@earendil-works/pi-ai';
import { randomUUID } from 'crypto';
import OpenAI from 'openai';

import {
  writeResponse,
  writeError,
  writeEvent,
  ErrorCodes,
  parseRequest
} from './rpc-protocol.js';
import { createEventHandler } from './event-mapper.js';

// ============================================================================
// Agnes AI Provider Registration
// ============================================================================

// Agnes AI 模型配置 (带有自定义 baseUrl)
const AGNES_MODELS = {
  'agnes-1.5-flash': {
    id: 'agnes-1.5-flash',
    provider: 'agnes',
    api: 'openai-responses',
    baseUrl: 'https://apihub.agnes-ai.com/v1',
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
  },
  'agnes-2.0-flash': {
    id: 'agnes-2.0-flash',
    provider: 'agnes',
    api: 'openai-responses',
    baseUrl: 'https://apihub.agnes-ai.com/v1',
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
  }
};

// Agnes AI OpenAI client
let agnesClient = null;

/**
 * Initialize Agnes AI client and provider
 */
function initAgnesAIProvider() {
  const apiKey = process.env.AGNES_API_KEY || process.env.OPENAI_API_KEY;
  if (!apiKey) {
    console.error('[AgnesAI] No API key found (AGNES_API_KEY or OPENAI_API_KEY)');
    return false;
  }

  // Create Agnes AI OpenAI client
  agnesClient = new OpenAI({
    apiKey,
    baseURL: 'https://apihub.agnes-ai.com/v1',
    dangerouslyAllowBrowser: false
  });

  console.log('[AgnesAI] Client initialized');
  return true;
}

// Initialize on startup
initAgnesAIProvider();

/**
 * Get Agnes AI model configuration
 * @param {string} modelId - Model identifier
 * @returns {Object} Model configuration with baseUrl
 */
function getAgnesModel(modelId) {
  return AGNES_MODELS[modelId] || {
    id: modelId,
    provider: 'agnes',
    api: 'openai-responses',
    baseUrl: 'https://apihub.agnes-ai.com/v1',
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
  };
}

/**
 * Create Agnes AI stream function
 * @param {Object} model - Model config with baseUrl
 * @returns {AsyncGenerator} Stream of assistant message events
 */
async function* agnesStream(model, context, options) {
  if (!agnesClient) {
    throw new Error('Agnes AI client not initialized');
  }

  try {
    // Format messages for Agnes AI
    const messages = [];
    if (context.systemPrompt) {
      messages.push({ role: 'system', content: context.systemPrompt });
    }
    for (const msg of context.messages || []) {
      if (msg.role === 'user') {
        messages.push({ role: 'user', content: typeof msg.content === 'string' ? msg.content : msg.content.map(c => c.text || '').join('') });
      } else if (msg.role === 'assistant') {
        messages.push({ role: 'assistant', content: typeof msg.content === 'string' ? msg.content : msg.content.map(c => c.text || '').join('') });
      }
    }

    const response = await agnesClient.responses.create({
      model: model.id,
      input: messages,
      max_tokens: options?.maxTokens || 4096
    }, { signal: options?.signal });

    // Build partial message for start event
    const partialMessage = {
      role: 'assistant',
      content: [],
      api: model.api,
      provider: model.provider,
      model: model.id,
      timestamp: Date.now()
    };

    // Yield start event with partial message
    yield { type: 'start', partial: partialMessage };

    // Process response - Agnes AI returns reasoning + message items
    let fullText = '';
    for (const item of response.output || []) {
      // Skip reasoning items, only process message items
      if (item.type === 'message' && item.role === 'assistant') {
        for (const content of item.content || []) {
          if (content.type === 'output_text') {
            fullText += content.text;
            // Yield text_delta for each text chunk (pi-agent-core expects this format)
            yield { type: 'text_delta', delta: content.text };
          }
        }
      }
    }

    // Yield done with final message
    const finalMessage = {
      ...partialMessage,
      content: [{ type: 'text', text: fullText }],
      stopReason: 'stop',
      usage: response.usage ? {
        input: response.usage.input_tokens || 0,
        output: response.usage.output_tokens || 0,
        cacheRead: response.usage.prompt_cache_hit_tokens || 0,
        cacheWrite: response.usage.prompt_cache_miss_tokens || 0,
        totalTokens: response.usage.total_tokens || 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
      } : { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } }
    };

    yield { type: 'done', message: finalMessage };
  } catch (error) {
    yield { type: 'error', error: error.message };
  }
}

// Register Agnes AI as a custom provider
if (agnesClient) {
  registerApiProvider({
    api: 'openai-responses',
    stream: agnesStream,
    streamSimple: agnesStream
  }, 'agnes-ai');
  console.log('[AgnesAI] Provider registered');
}

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
  defaultModel: process.env.PI_MODEL || 'agnes/agnes-1.5-flash',  // Agnes AI as default
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

    // Use getAgnesModel for Agnes AI models, otherwise use getModel
    let modelConfig_obj;
    let streamFn = null;
    if (modelConfig.provider === 'agnes') {
      modelConfig_obj = getAgnesModel(modelConfig.model);
      streamFn = agnesStream;  // Use Agnes stream function
    } else {
      modelConfig_obj = getModel(modelConfig.provider, modelConfig.model);
    }

    const agent = new Agent({
      initialState: {
        systemPrompt: systemPrompt || 'You are a helpful SOC analyst assistant.',
        model: modelConfig_obj
      },
      tools: [],
      streamFn: streamFn  // Pass custom stream function for Agnes AI
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