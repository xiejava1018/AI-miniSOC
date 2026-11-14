# 2026-11-14 Art Bot 无响应根治：配置中心统一 + 三层吞错链

> 事故：102 上 Art Bot 聊天「没反应」——SSE 只回 `data: [DONE]`，无内容无报错，
> DB 只落 user 消息，后端日志零错误。commit：`d255430`。

## 根因（两个独立缺陷叠加）

### 缺陷 1：模型硬编码，配置中心改了也没用

```python
# pi_agent_chat_service.py（改前）
DEFAULT_MODEL = "agnes/agnes-2.0-flash"   # 写死
```

Art Bot 走 pi_agent 后端 → Node runner，与「配置中心 → AI 模型管理」（soc_ai_providers）
**完全两条链路**。而 Agnes AI 免费额度打满：

```
POST https://apihub.agnes-ai.com/v1/responses  model=agnes-2.0-flash
→ HTTP 429 "You've reached the API rate limit for free users"
```

（先报 500 get_channel_failed，反复试后稳定 429——模型名是对的，是配额满了。
对照：GLM 同机直连 200 正常。）

### 缺陷 2：LLM 错误被三层静默吞掉（为什么是「没反应」而不是「报错」）

| 层 | 位置 | 问题 |
|---|---|---|
| Node runner | Agnes stream 的 catch | `yield {type:'error'}` → pi-agent-core 不认这个事件类型 |
| event-mapper | `message_end` 分支 | error 分支从未被触发（上游没发 error 事件） |
| Python | `stream_chat` 消费循环 | 只认 `delta` 和 `agent_end`，**没有 error 分支** |

pi-agent-core 的 `streamAssistantResponse` 对 error 事件的处理是
`case "error": const finalMessage = await response.result();`——而 EventStream 对 error
事件 **resolve(event.error)**（不 reject）→ `agent.prompt()` 正常返回 → 错误彻底消失。
`journalctl` 里一条 chat 错误都没有，就是这个原因。

## 修复（commit d255430）

1. **新增 `art_bot_model_resolver.py`**：复用已有的
   `data_source_resolver.resolve_ai(scene="chat")`（该 resolver 本来就支持 chat 场景，
   只是 Art Bot 没用它）。优先级：scenes 含 "chat" → is_default → 任一启用 → env GLM 回落 →
   全停用则不可用。解析结果经 env（PI_MODEL/PI_BASE_URL/PI_API_KEY/PI_API...）传给 runner，
   api_key 只在内存不落日志。
2. **runner 新增通用 OpenAI 兼容 provider**（configCenterStream）：支持
   openai-completions（GLM/DeepSeek）和 openai-responses（Agnes）两种协议。
3. **修三层吞错**：runner 把 LLM 错误 push 成 error 事件 → event-mapper 识别
   message_end 里的错误载荷（字符串 / {error} / {stopReason:'error'} 三种形态）→
   Python 消费循环新增 error 分支抛 `PiAgentChatError` → SSE 报错给前端。
4. **timeout 语义区分**：`soc_ai_providers.timeout_seconds` 是连通性测试超时
   （默认 5s），推理必超时 → 推理用 120s 兜底（`ART_BOT_TIMEOUT_SECONDS` 可覆盖，
   配置值 ≥30s 才采纳）。

## ⚠️ 最硬的坑：pi-agent-core streamFn 契约

**streamFn 返回值必须带 `.result()` 方法**（返回 Promise），不能是普通 async generator。
否则 `streamAssistantResponse` 调 `response.result()` 报
`"response.result is not a function"`——而这个错误本身又被同一机制吞掉，
**现象和 LLM 报错一模一样（聊天没反应）**。

pi-ai 没从主入口导出 `AssistantMessageEventStream`，runner 里内联实现了等价的
`createEventStream()`（push/iterator/result，语义与 pi-ai 原生一致：error 事件
resolve(error) 不 reject——错误传播靠 event-mapper，不靠 promise rejection）。

## 验证要点

- runner 层：正确 key → `text_delta`「我是一个」；错误 key → `type:"error"` +
  「401 令牌已过期或验证不正确」（改前是静默 message_end 空流）
- 后端 SSE：`data: {"delta":"我是"}` + assistant 落库
- 日志出现：`Art Bot 使用配置中心 AI 模型: provider=glm-main model=glm-4-flash
  api=openai-completions timeout=120s origin=db:glm-main`
- 102 实测：`data: {"delta": "你好"}`，DB 落 assistant 消息

## 附带发现

- `pi_agent_chat_service.py` 的 DEFAULT_MODEL 硬编码使 `.env` 的 AGNES_MODEL 对新会话无效
  （create_session 走常量）——与 §4.6「配置中心迁移后 env 键失效」同类问题
- 调 chat API 的 body 是 `{"message":{"role":"user","content":"..."}}`（message 是对象，
  传字符串会 422）
