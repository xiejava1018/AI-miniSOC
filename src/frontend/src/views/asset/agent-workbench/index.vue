<!--
  数字员工统一对话工作空间（OH-UI.6）

  v1：以 S9 资产问答为第一工具入口的对话页。
    - 多轮：靠后端 session_id 续接；本页维护当前会话消息列表。
    - 透明：每条回答展示 level/intent 徽标、参数、覆盖率/降级提示，
      不把 unsupported/unavailable 包装成成功答案。
  边界（诚实披露）：
    - v1 只接入资产问答工具；其它工具（融合/整改/优先级等）的统一
      编排是后续增强，本页不伪装成「全工具 agent」。
    - 非流式：/assets/ask 是请求-响应，等待期间显示加载态。
-->
<template>
  <div class="agent-workbench art-full-height">
    <div class="chat-shell">
      <!-- 头部 -->
      <div class="chat-header">
        <div class="title">
          <ElIcon class="robot-icon"><Service /></ElIcon>
          <span>资产数字员工</span>
        </div>
        <ElTooltip content="清空当前会话，开始新对话" placement="bottom">
          <ElButton text @click="newSession">
            <ElIcon><Plus /></ElIcon>新对话
          </ElButton>
        </ElTooltip>
      </div>

      <!-- 消息区 -->
      <div ref="msgBody" class="msg-body" v-loading="sending">
        <div v-if="messages.length === 0" class="welcome">
          <ElEmpty description="向资产数字员工提问，支持多轮对话">
            <div class="suggestions">
              <ElTag
                v-for="q in suggestions"
                :key="q"
                class="sugg-tag"
                @click="send(q)"
              >
                {{ q }}
              </ElTag>
            </div>
          </ElEmpty>
        </div>

        <template v-for="(m, i) in messages" :key="i">
          <!-- 用户消息 -->
          <div v-if="m.role === 'user'" class="msg-row user">
            <div class="bubble user">{{ m.content }}</div>
          </div>
          <!-- 助手消息 -->
          <div v-else class="msg-row assistant">
            <ElAvatar class="avatar" :size="32">
              <ElIcon><Service /></ElIcon>
            </ElAvatar>
            <div class="bubble assistant">
              <div class="answer-text">{{ m.text }}</div>

              <!-- 徽标 -->
              <div class="chips">
                <ElTag size="small" :type="m.level === 'L2' ? 'success' : 'info'">
                  {{ m.level }}
                </ElTag>
                <ElTag size="small"
                        :type="intentTagType(m.intent)">
                  {{ intentLabel[m.intent || ''] || m.intent }}
                </ElTag>
                <ElTag v-if="m.template_id" size="small" type="warning">
                  {{ m.template_id }}
                </ElTag>
              </div>

              <!-- 参数 -->
              <div v-if="hasObj(m.params)" class="meta">
                <span class="meta-label">参数：</span>
                <code>{{ compact(m.params) }}</code>
              </div>

              <!-- 统计 -->
              <div v-if="hasObj(m.stats)" class="meta">
                <span class="meta-label">统计：</span>
                <code>{{ compact(m.stats) }}</code>
              </div>

              <!-- 覆盖率披露 -->
              <div v-if="m.coverage && (m.coverage.missing || m.coverage.unknown)"
                   class="meta coverage">
                <ElIcon><WarningFilled /></ElIcon>
                数据覆盖：已计 {{ m.coverage.counted ?? '-' }} /
                缺失 {{ m.coverage.missing ?? '-' }} /
                未知 {{ m.coverage.unknown ?? '-' }}
              </div>

              <!-- 降级 -->
              <div v-if="m.data_degraded" class="meta degraded">
                <ElIcon><WarningFilled /></ElIcon>
                部分数据源不可达，结果可能不全
              </div>

              <!-- 备注 -->
              <div v-if="m.notes && m.notes.length" class="meta">
                <div v-for="(n, ni) in m.notes" :key="ni" class="note">· {{ n }}</div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        <ElInput
          v-model="draft"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入资产相关问题，Enter 发送（Shift+Enter 换行）"
          :disabled="sending"
          @keydown.enter.exact.prevent="onEnter"
        />
        <ElButton type="primary" :loading="sending"
                  :disabled="!draft.trim()" @click="onEnter">
          发送
        </ElButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Service, WarningFilled } from '@element-plus/icons-vue'
import { askAssetQuery, type AskResult } from '@/api/asset'

defineOptions({ name: 'AssetAgentWorkbench' })

interface UIMsg {
  role: 'user' | 'assistant'
  content?: string
  text?: string
  level?: string
  intent?: string
  template_id?: string
  params?: any
  stats?: any
  coverage?: AskResult['coverage']
  data_degraded?: boolean
  notes?: string[]
}

const messages = ref<UIMsg[]>([])
const draft = ref('')
const sending = ref(false)
const sessionId = ref<string | null>(null)
const msgBody = ref<HTMLElement>()

const suggestions = [
  '哪些资产开放了 3389 端口？',
  '按操作系统统计资产数量',
  '有多少台离线资产？',
  '192.168.0.30 这台资产的风险情况？',
]

const okIntents = ['filter', 'stats', 'detail', 'template']
const intentLabel: Record<string, string> = {
  filter: '筛选', stats: '统计', detail: '详情', template: '模板',
  unsupported: '不支持', unavailable: '不可用',
  invalid_params: '参数无效', error: '错误',
}

function hasObj(o: any) {
  return o && Object.keys(o).length > 0
}

function intentTagType(intent?: string): 'primary' | 'danger' {
  return intent && okIntents.includes(intent) ? 'primary' : 'danger'
}
function compact(o: any) {
  return JSON.stringify(o)
}

async function scrollDown() {
  await nextTick()
  const el = msgBody.value
  if (el) el.scrollTop = el.scrollHeight
}

async function send(text: string) {
  const q = text.trim()
  if (!q || sending.value) return
  messages.value.push({ role: 'user', content: q })
  sending.value = true
  await scrollDown()
  try {
    const resp = await askAssetQuery(q, sessionId.value || undefined)
    if (resp?.code === 200 && resp.data) {
      const d = resp.data
      if (d.session_id) sessionId.value = d.session_id
      const answer =
        d.summary || d.message ||
        (d.intent === 'unsupported' ? '该问题暂不支持，请换一种问法。' : '—')
      messages.value.push({
        role: 'assistant',
        text: answer,
        level: d.level,
        intent: d.intent,
        template_id: d.template_id,
        params: d.params,
        stats: d.stats,
        coverage: d.coverage,
        data_degraded: d.data_degraded,
        notes: d.notes,
      })
    } else {
      ElMessage.error(resp?.msg || '查询失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '请求失败')
  } finally {
    sending.value = false
    scrollDown()
  }
}

function onEnter() {
  const q = draft.value
  if (!q.trim()) return
  draft.value = ''
  send(q)
}

function newSession() {
  messages.value = []
  sessionId.value = null
  draft.value = ''
}
</script>

<style scoped>
.agent-workbench {
  padding: 8px;
}
.chat-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 15px;
}
.robot-icon {
  color: var(--el-color-primary);
  font-size: 18px;
}
.msg-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
}
.welcome {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 12px;
}
.sugg-tag {
  cursor: pointer;
}
.msg-row {
  display: flex;
  margin-bottom: 16px;
}
.msg-row.user {
  justify-content: flex-end;
}
.avatar {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
  margin-right: 10px;
  flex: none;
}
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
}
.bubble.user {
  background: var(--el-color-primary);
  color: #fff;
}
.bubble.assistant {
  background: var(--el-fill-color-light);
}
.answer-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.chips {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.meta code {
  background: var(--el-bg-color);
  padding: 1px 5px;
  border-radius: 3px;
}
.meta-label {
  color: var(--el-text-color-placeholder);
}
.coverage, .degraded {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--el-color-warning);
}
.note {
  line-height: 1.6;
}
.input-area {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.input-area .el-textarea {
  flex: 1;
}
</style>
