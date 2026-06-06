/**
 * Markdown 渲染工具
 *
 * 用于 Art Bot 聊天消息：marked 解析 + DOMPurify 清洗 + highlight.js 代码高亮。
 * 输出 HTML 字符串，供 v-html 渲染。
 *
 * 注意：
 * - 必须在 v-html 之前 sanitize，否则存在 XSS 风险
 * - 代码块 language-* 由 highlight.js 自动识别
 */

import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'

// marked v14 renderer 通过 marked.use({ renderer }) 注入
// 用局部 any 避免与 v14 复杂的 MarkedExtension 类型搏斗
const codeRenderer = {
  code(code: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        const out = hljs.highlight(code, { language: lang, ignoreIllegals: true })
        return `<pre class="hljs"><code class="language-${lang}">${out.value}</code></pre>`
      } catch {
        /* fall through */
      }
    }
    const escaped = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return `<pre class="hljs"><code>${escaped}</code></pre>`
  }
}
// marked v14 期望 MarkedExtension；这里用 any 注入实际可工作的 renderer
marked.use({ renderer: codeRenderer } as any)

marked.setOptions({
  gfm: true,
  breaks: true
})

/**
 * 把 Markdown 文本渲染成安全 HTML 字符串。
 * 任何使用方必须通过 v-html 渲染此输出。
 */
export function renderMarkdown(input: string | null | undefined): string {
  if (!input) return ''
  // marked.parse 可能是同步 string 或异步 Promise，统一走 async 路径
  const raw = marked.parse(input, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { html: true },
    // 允许 highlight.js 注入的 class
    ADD_ATTR: ['class', 'target', 'rel']
  })
}
