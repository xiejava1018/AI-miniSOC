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
// Generic OpenAI-compatible Provider (配置中心 → AI 模型管理)
// ============================================================================
//
// 2026-11-10：Art Bot 改为使用「配置中心 → AI 模型管理」里的模型实例，
// 由 Python 后端通过环境变量传入：
//   PI_MODEL           = "<provider_code>/<model_name>"
//   PI_PROVIDER_CODE   = "<provider_code>"
//   PI_BASE_URL        = "<base_url>"        （OpenAI 兼容 base，不以 / 结尾）
//   PI_API_KEY         = "<解密后的 api key>"
//   PI_API             = "openai-completions" | "openai-responses"
//   PI_MAX_TOKENS      = "<max_tokens>"      （可选）
//   PI_TIMEOUT_SECONDS = "<timeout_seconds>" （可选）
//
// 之前模型名硬编码在 Python 侧（agnes/agnes-2.0-flash），配置中心改了也没用。
// 现在这一层只负责「拿到配置 → 建 client → 注册 provider」。

const PI_API_TYPE = process.env.PI_API || 'openai-completions';
const PI_BASE_URL = process.env.PI_BASE_URL || '';
const PI_API_KEY = process.env.PI_API_KEY || '';
const PI_MAX_TOKENS = process.env.PI_MAX_TOKENS
  ? parseInt(process.env.PI_MAX_TOKENS, 10)
  : undefined;
const PI_TIMEOUT_SECONDS = process.env.PI_TIMEOUT_SECONDS
  ? parseInt(process.env.PI_TIMEOUT_SECONDS, 10)
  : undefined;

/**
 * 构造 pi-ai 的 model 描述对象。
 * pi-ai 的 stream 实现会用 model.baseUrl / model.id / model.api，
 * api key 从 options.apiKey 或 env 拿（我们走 PI_API_KEY 显式传入）。
 */
function buildConfigCenterModel(modelId) {
  const providerCode = process.env.PI_PROVIDER_CODE || 'config-center';
  return {
    id: modelId,
    provider: providerCode,
    api: PI_API_TYPE,
    baseUrl: PI_BASE_URL || undefined,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
  };
}

/**
 * 极简版 AssistantMessageEventStream（不依赖 pi-ai 内部路径）。
 *
 * ⚠️ 契约（踩坑记录）：
 * pi-agent-core 的 streamAssistantResponse 拿到 streamFn 的返回值后，
 * 会调用 ``response.result()`` 取最终消息 —— 所以返回值**必须**带
 * ``.result()`` 方法（返回 Promise），不能是普通 async generator
 * （否则报 "response.result is not a function"，错误又被静默吞掉，
 *  表现为「聊天没反应」）。
 *
 * 语义与 pi-ai 的 AssistantMessageEventStream 一致：
 *  - push({type:'done', message})  → result() resolve(message)
 *  - push({type:'error', error})   → result() resolve(error)（**不 reject**）
 *    这正是 pi-agent-core 吞错的原因：它 case "error" 拿 result() 后
 *    当成正常 finalMessage 继续走。event-mapper 会识别并转 agent_error。
 */
function createEventStream() {
  const queue = [];
  const waiting = [];
  let done = false;
  let resolveFinalResult;
  const finalResultPromise = new Promise((resolve) => { resolveFinalResult = resolve; });

  return {
    push(event) {
      if (done) return;
      if (event.type === 'done' || event.type === 'error') {
        done = true;
        resolveFinalResult(event.type === 'done' ? event.message : event.error);
      }
      const waiter = waiting.shift();
      if (waiter) waiter({ value: event, done: false });
      else queue.push(event);
    },
    end(result) {
      done = true;
      if (result !== undefined) resolveFinalResult(result);
      while (waiting.length > 0) waiting.shift()({ value: undefined, done: true });
    },
    async *[Symbol.asyncIterator]() {
      for (;;) {
        if (queue.length > 0) {
          yield queue.shift();
        } else if (done) {
          return;
        } else {
          const r = await new Promise((resolve) => waiting.push(resolve));
          if (r.done) return;
          yield r.value;
        }
      }
    },
    result() { return finalResultPromise; }
  };
}

/**
 * 通用 OpenAI 兼容 stream（chat/completions 与 responses 两种协议）。
 * 详见 createEventStream 上方的契约说明。
 */
function configCenterStream(model, context, options) {
  const stream = createEventStream();

  (async () => {
    const apiKey = options?.apiKey || PI_API_KEY || process.env.OPENAI_API_KEY;
    const partialMessage = {
      role: 'assistant',
      content: [],
      api: model.api,
      provider: model.provider,
      model: model.id,
      timestamp: Date.now()
    };

    if (!apiKey) {
      stream.push({
        type: 'error',
        error: 'No API key for config-center provider (PI_API_KEY 未设置)'
      });
      return;
    }

    const client = new OpenAI({
      apiKey,
      baseURL: model.baseUrl,
      timeout: PI_TIMEOUT_SECONDS ? PI_TIMEOUT_SECONDS * 1000 : undefined,
      dangerouslyAllowBrowser: false
    });

    const messages = [];
    if (context.systemPrompt) {
      messages.push({ role: 'system', content: context.systemPrompt });
    }
    for (const msg of context.messages || []) {
      const text = typeof msg.content === 'string'
        ? msg.content
        : (msg.content || []).map((c) => c.text || '').join('');
      messages.push({
        role: msg.role === 'assistant' ? 'assistant' : 'user',
        content: text
      });
    }

    let fullText = '';

    try {
      stream.push({ type: 'start', partial: partialMessage });

      if (model.api === 'openai-responses') {
        const response = await client.responses.create(
          {
            model: model.id,
            input: messages,
            max_tokens: options?.maxTokens || PI_MAX_TOKENS || 4096
          },
          { signal: options?.signal }
        );
        for (const item of response.output || []) {
          if (item.type === 'message' && item.role === 'assistant') {
            for (const content of item.content || []) {
              if (content.type === 'output_text') {
                fullText += content.text;
                stream.push({ type: 'text_delta', delta: content.text });
              }
            }
          }
        }
      } else {
        const chunkStream = await client.chat.completions.create(
          {
            model: model.id,
            messages,
            stream: true,
            max_tokens: options?.maxTokens || PI_MAX_TOKENS
          },
          { signal: options?.signal }
        );
        for await (const chunk of chunkStream) {
          const delta = chunk.choices?.[0]?.delta?.content;
          if (delta) {
            fullText += delta;
            stream.push({ type: 'text_delta', delta });
          }
        }
      }

      stream.push({
        type: 'done',
        message: {
          ...partialMessage,
          content: [{ type: 'text', text: fullText }],
          stopReason: 'stop',
          usage: {
            input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
          }
        }
      });
    } catch (error) {
      // 关键：把 LLM 错误（429 额度用尽 / 401 key 错 / 5xx）变成 error 事件。
      // AssistantMessageEventStream 对 error 事件 **resolve(event.error)**
      // （不 reject），pi-agent-core 会走 case "error" → response.result()
      // 拿到 error → emit message_end（message 就是那个 error）。
      // event-mapper 会识别它并转成 agent_error → Python → SSE 报错给前端。
      stream.push({
        type: 'error',
        error: error?.message || String(error)
      });
    }
  })();

  return stream;
}

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
    // 2026-11-10 修（静默吞错的根因）：
    // pi-agent-core 的 streamAssistantResponse 对 `error` 事件的处理是
    //   case "error": const finalMessage = await response.result();
    // 而 AssistantMessageEventStream 的 extractResult 对 error 事件
    // **return event.error**（resolve，不是 reject）→ agent.prompt() 正常返回，
    // 错误就此消失（前端只收到 [DONE]，表现为「聊天没反应」）。
    //
    // 正确做法：yield 一个 error 事件（不是 throw）。
    // pi-agent-core 会走 case "error" → response.result() 拿到 error → emit
    // message_end；同时我们把原始错误也 yield 出去，让 event-mapper 转成
    // agent_error 事件 → Python → SSE 报错给前端。
    yield { type: 'error', error: error.message, errorDetail: error };
    // 结束流，避免继续往下走
    return;
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

// Register the generic OpenAI-compatible provider from the config center.
// PI_API decides which api type is used (openai-completions / openai-responses).
// Registering a distinct api type avoids conflicting with the built-in ones.
if (PI_BASE_URL && PI_API_KEY) {
  registerApiProvider({
    api: PI_API_TYPE,
    stream: configCenterStream,
    streamSimple: configCenterStream
  }, 'config-center');
  console.log(
    `[ConfigCenter] Provider registered: api=${PI_API_TYPE} baseUrl=${PI_BASE_URL} model=${process.env.PI_MODEL}`
  );
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
    } else if (PI_BASE_URL && PI_API_KEY) {
      // Provider from the config center (AI model management) — baseUrl / api key /
      // api type all come from env vars passed in by the Python backend.
      modelConfig_obj = buildConfigCenterModel(modelConfig.model);
      streamFn = configCenterStream;
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