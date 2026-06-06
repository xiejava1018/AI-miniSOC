/**
 * SSE 流式工具
 *
 * 使用 fetch + ReadableStream 解码 `text/event-stream`。
 * 故意绕开 axios — 后者的 transformResponse 会拦截所有响应流。
 *
 * 用法：
 *   const stop = postStream('/ai/chat', { message: { role: 'user', content: 'hi' } },
 *     { onDelta: (chunk) => messages.value.push(chunk) })
 *   // 中途取消：stop()
 */

import { useUserStore } from '@/store/modules/user'

export interface StreamHandlers {
  onDelta?: (piece: string) => void
  onError?: (err: Error) => void
  onDone?: () => void
  onOpen?: (res: Response) => void
}

export interface StreamOptions extends StreamHandlers {
  /** 透传后端 X-Session-Id 等自定义头到回调 */
  onHeaders?: (headers: Headers) => void
  /** 取消信号 */
  signal?: AbortSignal
}

const API_PREFIX = '/api/v1'

/**
 * POST + SSE 订阅
 * @param url 相对路径（不含 /api/v1 前缀）或绝对路径
 * @param body 请求体（自动 JSON.stringify）
 * @param opts 回调 / 取消信号
 * @returns abort 函数（调用后立即中断 fetch）
 */
export function postStream<T = unknown>(
  url: string,
  body: T,
  opts: StreamOptions = {}
): () => void {
  const userStore = useUserStore()
  const fullUrl = url.startsWith('http') ? url : `${API_PREFIX}${url}`

  const controller = new AbortController()
  // 透传外部 signal
  if (opts.signal) {
    opts.signal.addEventListener('abort', () => controller.abort())
  }

  fetch(fullUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(userStore.accessToken ? { Authorization: `Bearer ${userStore.accessToken}` } : {})
    },
    body: JSON.stringify(body),
    signal: controller.signal
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => '')
        const err = new Error(`SSE request failed: ${res.status} ${text}`)
        opts.onError?.(err)
        opts.onDone?.()
        return
      }

      opts.onOpen?.(res)
      opts.onHeaders?.(res.headers)

      const reader = res.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      try {
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          // 按 \n\n 切分事件（SSE 规范）
          let sepIdx: number
          while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
            const rawEvent = buffer.slice(0, sepIdx)
            buffer = buffer.slice(sepIdx + 2)
            const piece = parseSseEvent(rawEvent)
            if (piece === null) continue
            if (piece === '[DONE]') {
              opts.onDone?.()
              return
            }
            opts.onDelta?.(piece)
          }
        }
        // 流结束未收到 [DONE]
        opts.onDone?.()
      } catch (e) {
        if ((e as Error).name === 'AbortError') {
          return // 主动取消，吞掉
        }
        opts.onError?.(e as Error)
        opts.onDone?.()
      }
    })
    .catch((e) => {
      if ((e as Error).name === 'AbortError') return
      opts.onError?.(e as Error)
      opts.onDone?.()
    })

  return () => controller.abort()
}

/**
 * 解析一段 SSE 事件块。
 * 形如：
 *   data: {"delta":"hi"}
 *   data: {"delta":" there"}
 *  返回拼接后的 data 字符串；空事件返回空串；[DONE] 返回字面量 '[DONE]'。
 */
function parseSseEvent(raw: string): string | null {
  const lines = raw.split('\n')
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('data:')) {
      // 注意 SSE 规范：'data:' 后允许一个空格，可选
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (dataLines.length === 0) return null
  const joined = dataLines.join('\n')
  // 尝试解析后端约定的 JSON；非 JSON 原样透传
  try {
    const obj = JSON.parse(joined) as { delta?: string; error?: string }
    if (typeof obj.delta === 'string') return obj.delta
    if (typeof obj.error === 'string') throw new Error(obj.error)
    return joined
  } catch {
    return joined
  }
}
