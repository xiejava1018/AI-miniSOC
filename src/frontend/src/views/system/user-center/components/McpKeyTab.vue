<!-- MCP 接入 Tab：Key 自助管理（申请/一次性明文/延期/注销/接入示例） -->
<template>
  <div class="mcp-key-tab">
    <ElAlert type="info" :closable="false" class="mb-4">
      MCP Key 是你接入 AI Agent（workbuddy / Claude 等）的凭证，权限等同你的账号角色。
      明文只在申请时展示一次，请立即保存。
    </ElAlert>

    <div class="flex-c justify-between mb-3">
      <span class="text-sm text-g-600">
        我的 Key（{{ keys.length }}<template v-if="canManage">/{{ maxKeysHint }}</template
        >）
      </span>
      <ElButton v-if="canManage" type="primary" size="small" @click="openCreateDialog()">
        <ArtSvgIcon icon="ri:add-line" class="mr-1" />
        申请新 Key
      </ElButton>
    </div>

    <!-- Key 卡片列表 -->
    <div v-loading="loading">
      <ElEmpty v-if="!loading && keys.length === 0" description="还没有 MCP Key" :image-size="80" />
      <div
        v-for="item in keys"
        :key="item.id"
        class="key-card art-card-sm mb-3 flex-c justify-between flex-wrap gap-2"
      >
        <div class="min-w-0">
          <div class="flex items-center flex-wrap gap-2">
            <ArtSvgIcon icon="ri:key-2-line" class="text-base" />
            <span class="font-medium">{{ item.name }}</span>
            <span class="text-xs text-g-500 font-mono">{{ item.key_prefix }}…</span>
            <ElTag v-if="keyState(item) === 'ok'" type="success" size="small" effect="light">
              剩余 {{ item.days_remaining }} 天
            </ElTag>
            <ElTag v-else-if="keyState(item) === 'warn'" type="warning" size="small" effect="light">
              即将过期（剩 {{ item.days_remaining }} 天）
            </ElTag>
            <ElTag v-else-if="keyState(item) === 'expired'" type="info" size="small" effect="light">
              已过期
            </ElTag>
            <ElTag v-else type="danger" size="small" effect="light">已注销</ElTag>
          </div>
          <div class="mt-1.5 text-xs text-g-500">
            最后使用：{{ formatTime(item.last_used_at) }} · 创建于：{{
              formatTime(item.created_at)
            }}
          </div>
        </div>
        <div class="flex-shrink-0 flex-c gap-2">
          <ElButton size="small" text type="primary" @click="openExampleDialog(item)">
            接入示例
          </ElButton>
          <template v-if="canManage">
            <ElButton
              v-if="keyState(item) === 'ok' || keyState(item) === 'warn'"
              size="small"
              text
              type="primary"
              @click="openExtendDialog(item)"
            >
              延期
            </ElButton>
            <ElButton
              v-if="keyState(item) === 'expired'"
              size="small"
              text
              type="primary"
              @click="openCreateDialog(item.name)"
            >
              重新申请
            </ElButton>
            <ElButton
              v-if="item.status === 'active'"
              size="small"
              text
              type="danger"
              @click="confirmRevoke(item)"
            >
              注销
            </ElButton>
            <ElButton
              v-if="item.status === 'revoked'"
              size="small"
              text
              type="danger"
              @click="confirmPurge(item)"
            >
              彻底删除
            </ElButton>
          </template>
        </div>
      </div>
    </div>

    <!-- 申请新 Key 弹窗 -->
    <ElDialog
      v-model="createDialog.visible"
      title="申请新 MCP Key"
      width="440px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <ElForm ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <ElFormItem label="名称" prop="name">
          <ElInput
            v-model="createForm.name"
            placeholder="用途标识，如 workbuddy / 我的Claude"
            maxlength="50"
            show-word-limit
          />
        </ElFormItem>
        <ElFormItem label="有效期" prop="validity_days">
          <ElSelect v-model="createForm.validity_days" style="width: 100%">
            <ElOption v-for="opt in validityOptions" :key="opt" :label="`${opt} 天`" :value="opt" />
            <ElOption label="自定义" :value="-1" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem v-if="createForm.validity_days === -1" label="天数" prop="custom_days">
          <ElInputNumber
            v-model="createForm.custom_days"
            :min="1"
            :max="365"
            style="width: 100%"
            placeholder="1-365 天"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="createDialog.visible = false">取消</ElButton>
        <ElButton type="primary" :loading="creating" @click="submitCreate">申请</ElButton>
      </template>
    </ElDialog>

    <!-- 申请成功：一次性明文展示 -->
    <ElDialog
      v-model="resultDialog.visible"
      title="Key 申请成功"
      width="560px"
      :close-on-click-modal="false"
      :show-close="false"
      destroy-on-close
    >
      <ElAlert type="warning" :closable="false" class="mb-4">
        <strong>关闭后无法再次查看此 Key 明文，请立即复制保存！</strong>
      </ElAlert>
      <div class="key-plaintext" @click="copyText(resultDialog.key?.key || '', 'Key 已复制')">
        <code>{{ resultDialog.key?.key }}</code>
        <ArtSvgIcon icon="ri:file-copy-line" class="copy-icon" />
      </div>
      <div class="mt-4 text-xs text-g-500 mb-1">workbuddy 接入配置（已填入此 Key）：</div>
      <pre class="config-snippet" @click="copyText(workbuddySnippet, '配置已复制')">{{
        workbuddySnippet
      }}</pre>
      <template #footer>
        <ElButton type="primary" @click="resultDialog.visible = false">我已保存，关闭</ElButton>
      </template>
    </ElDialog>

    <!-- 延期弹窗 -->
    <ElDialog
      v-model="extendDialog.visible"
      title="延期 Key"
      width="400px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <ElForm label-width="90px">
        <ElFormItem label="Key">
          <span class="text-xs font-mono"
            >{{ extendDialog.item?.name }}（{{ extendDialog.item?.key_prefix }}…）</span
          >
        </ElFormItem>
        <ElFormItem label="新有效期">
          <ElSelect v-model="extendDialog.days" style="width: 100%">
            <ElOption v-for="opt in validityOptions" :key="opt" :label="`${opt} 天`" :value="opt" />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="extendDialog.visible = false">取消</ElButton>
        <ElButton type="primary" :loading="extending" @click="submitExtend">确认延期</ElButton>
      </template>
    </ElDialog>

    <!-- 接入示例弹窗 -->
    <ElDialog
      v-model="exampleDialog.visible"
      title="Agent 接入配置示例"
      width="620px"
      destroy-on-close
    >
      <div class="mb-3 text-xs text-g-500">
        服务地址：<code>{{ mcpServiceUrl }}</code> · 请把
        <code>&lt;你的Key&gt;</code> 替换为申请时保存的完整 Key 明文 （示例 Key：{{
          exampleDialog.item?.key_prefix
        }}…）。
      </div>
      <ElTabs>
        <ElTabPane label="workbuddy">
          <pre class="config-snippet" @click="copyText(exampleWorkbuddy, '已复制')">{{
            exampleWorkbuddy
          }}</pre>
        </ElTabPane>
        <ElTabPane label="Claude Code">
          <pre class="config-snippet" @click="copyText(exampleClaude, '已复制')">{{
            exampleClaude
          }}</pre>
        </ElTabPane>
        <ElTabPane label="Cursor">
          <pre class="config-snippet" @click="copyText(exampleCursor, '已复制')">{{
            exampleCursor
          }}</pre>
        </ElTabPane>
      </ElTabs>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, ElMessageBox } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'
  import {
    fetchGetMyMcpKeys,
    fetchCreateMyMcpKey,
    fetchExtendMyMcpKey,
    fetchRevokeMyMcpKey,
    fetchPurgeMyMcpKey,
    type McpKeyItem,
    type McpKeyCreated
  } from '@/api/user-center'
  import { useSystemStore } from '@/store/modules/system'

  defineOptions({ name: 'McpKeyTab' })

  const systemStore = useSystemStore()

  const props = defineProps<{
    /** viewer/auditor/readonly 不可自助管理（后端同样校验 403） */
    roleCode?: string | null
  }>()

  const canManage = computed(
    () => !['viewer', 'auditor', 'readonly'].includes(props.roleCode || '')
  )
  const maxKeysHint = 5
  const validityOptions = [7, 30, 90, 365]

  const loading = ref(false)
  const keys = ref<McpKeyItem[]>([])

  const loadKeys = async () => {
    loading.value = true
    try {
      keys.value = await fetchGetMyMcpKeys()
    } catch (e) {
      console.error('加载 MCP Key 失败', e)
    } finally {
      loading.value = false
    }
  }

  onMounted(loadKeys)

  /** key 状态派生：ok=正常 warn=≤7天 expired=已过期 revoked=已注销 */
  const keyState = (item: McpKeyItem): 'ok' | 'warn' | 'expired' | 'revoked' => {
    if (item.status === 'revoked') return 'revoked'
    if (item.days_remaining === null || item.days_remaining <= 0) return 'expired'
    if (item.days_remaining <= 7) return 'warn'
    return 'ok'
  }

  const formatTime = (t?: string | null): string => {
    if (!t) return '从未使用'
    const d = new Date(t)
    if (Number.isNaN(d.getTime())) return t
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }

  const copyText = async (text: string, tip = '已复制') => {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(tip)
    } catch {
      ElMessage.warning('复制失败，请手动选择复制')
    }
  }

  // ---------- 申请 ----------
  const createDialog = reactive({ visible: false })
  const createFormRef = ref<FormInstance>()
  const creating = ref(false)
  const createForm = reactive({
    name: '',
    validity_days: 30 as number,
    custom_days: 90
  })
  const createRules: FormRules = {
    name: [
      { required: true, message: '请输入 Key 名称', trigger: 'blur' },
      { min: 1, max: 50, message: '长度 1-50 字符', trigger: 'blur' }
    ],
    custom_days: [{ required: true, message: '请输入自定义天数', trigger: 'blur' }]
  }

  const openCreateDialog = (presetName?: string) => {
    createForm.name = presetName || ''
    createForm.validity_days = 30
    createForm.custom_days = 90
    createDialog.visible = true
  }

  const resultDialog = reactive<{ visible: boolean; key: McpKeyCreated | null }>({
    visible: false,
    key: null
  })

  /**
   * MCP 客户端接入地址
   *
   * 解析优先级：
   * 1. 运维在配置中心「general → mcp_public_url」显式配置的对外地址（最准）
   * 2. 当前访问的 origin + /mcp（兜底）
   *
   * 历史 bug：曾硬编码 `http://{hostname}:8100/mcp`。
   * 8100 是 MCP 独立进程的**内网**监听端口，公网并不通
   * （公网链路是 Cloudflare Tunnel → nginx:8080 → 反代 127.0.0.1:8100），
   * 用户把带 8100 的地址粘进客户端必然「连接超时」。
   * 因此这里绝不能再拼 8100 端口，也不再强制 http。
   */
  const mcpServiceUrl = computed(() => {
    // 1. 后端下发（运维显式配置）
    const configured = systemStore.mcpPublicUrl
    if (configured) return configured.replace(/\/+$/, '')

    // 2. 兜底：按当前访问 origin 推导
    //    origin 已含协议与端口（http/https + 实际端口），不额外拼 8100。
    //    前端是 SPA，pathname 形如 /user-center/xxx —— MCP 端点挂在站点根路径下，
    //    所以这里只用 origin。
    return `${window.location.origin}/mcp`
  })

  const buildWorkbuddyJson = (key: string) =>
    JSON.stringify(
      {
        mcpServers: {
          'ai-mini-soc': {
            url: mcpServiceUrl.value,
            headers: { Authorization: `Bearer ${key}` },
            disabled: false
          }
        }
      },
      null,
      2
    )

  /** 结果弹窗里的 workbuddy 片段（含真实新 Key） */
  const workbuddySnippet = computed(() =>
    resultDialog.key ? buildWorkbuddyJson(resultDialog.key.key) : ''
  )

  const submitCreate = async () => {
    if (!createFormRef.value) return
    try {
      await createFormRef.value.validate()
    } catch {
      return
    }
    const days = createForm.validity_days === -1 ? createForm.custom_days : createForm.validity_days
    creating.value = true
    try {
      const created = await fetchCreateMyMcpKey({
        name: createForm.name.trim(),
        validity_days: days
      })
      resultDialog.key = created
      resultDialog.visible = true
      createDialog.visible = false
      await loadKeys()
    } catch (e: any) {
      // 拦截器已对业务码错误弹过提示；此处兜底网络异常
      console.error('申请 Key 失败', e)
    } finally {
      creating.value = false
    }
  }

  // ---------- 延期 ----------
  const extendDialog = reactive<{ visible: boolean; item: McpKeyItem | null; days: number }>({
    visible: false,
    item: null,
    days: 30
  })
  const extending = ref(false)

  const openExtendDialog = (item: McpKeyItem) => {
    extendDialog.item = item
    extendDialog.days = 30
    extendDialog.visible = true
  }

  const submitExtend = async () => {
    if (!extendDialog.item) return
    extending.value = true
    try {
      await fetchExtendMyMcpKey(extendDialog.item.id, extendDialog.days)
      ElMessage.success('延期成功')
      extendDialog.visible = false
      await loadKeys()
    } catch (e) {
      console.error('延期失败', e)
    } finally {
      extending.value = false
    }
  }

  // ---------- 注销（输入名称确认防误触） ----------
  const confirmRevoke = (item: McpKeyItem) => {
    ElMessageBox.prompt(
      `注销后使用此 Key 的 Agent 将立即无法访问。输入 Key 名称「${item.name}」确认注销：`,
      '注销 Key',
      {
        confirmButtonText: '确认注销',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        inputValidator: (v: string) => v.trim() === item.name || `请输入「${item.name}」以确认`
      }
    )
      .then(async ({ value }) => {
        if (value.trim() !== item.name) return
        try {
          await fetchRevokeMyMcpKey(item.id)
          ElMessage.success('已注销')
          await loadKeys()
        } catch (e) {
          console.error('注销失败', e)
        }
      })
      .catch(() => {})
  }

  // ---------- 彻底删除已注销 Key（双步走：先 revoke 留审计，再 purge 物理消解）----------
  const confirmPurge = (item: McpKeyItem) => {
    ElMessageBox.prompt(
      `彻底删除是物理消解，DB 记录会被永久删除（仅审计哈希链留痕）。\n\n` +
      `Key 名称「${item.name}」将不可恢复，Agent 再也无法复用。\n\n` +
      `输入 Key 名称「${item.name}」以确认：`,
      '彻底删除已注销 Key',
      {
        confirmButtonText: '确认彻底删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        inputValidator: (v: string) => v.trim() === item.name || `请输入「${item.name}」以确认`
      }
    )
      .then(async ({ value }) => {
        if (value.trim() !== item.name) return
        try {
          await fetchPurgeMyMcpKey(item.id)
          ElMessage.success('已彻底删除')
          await loadKeys()
        } catch (e) {
          console.error('彻底删除失败', e)
        }
      })
      .catch(() => {})
  }

  // ---------- 接入示例 ----------
  const exampleDialog = reactive<{ visible: boolean; item: McpKeyItem | null }>({
    visible: false,
    item: null
  })

  const openExampleDialog = (item: McpKeyItem) => {
    exampleDialog.item = item
    exampleDialog.visible = true
  }

  const exampleWorkbuddy = computed(() => buildWorkbuddyJson('<你的Key>'))
  const exampleClaude = computed(
    () =>
      `claude mcp add --transport http ai-mini-soc ${mcpServiceUrl.value} -H "Authorization: Bearer <你的Key>"`
  )
  const exampleCursor = computed(() =>
    JSON.stringify(
      {
        mcpServers: {
          'ai-mini-soc': {
            url: mcpServiceUrl.value,
            headers: { Authorization: 'Bearer <你的Key>' }
          }
        }
      },
      null,
      2
    )
  )

  defineExpose({ loadKeys })
</script>

<style scoped lang="scss">
  .key-card {
    padding: 14px 18px;
  }

  .key-plaintext {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 12px 14px;
    cursor: pointer;
    word-break: break-all;
    background-color: var(--art-gray-100);
    border-radius: 6px;

    code {
      font-size: 14px;
      font-weight: 600;
      color: var(--art-main-danger-color, #f56c6c);
    }

    .copy-icon {
      flex-shrink: 0;
      font-size: 18px;
    }
  }

  .config-snippet {
    position: relative;
    padding: 12px 14px;
    margin: 0;
    overflow-x: auto;
    font-size: 12px;
    line-height: 1.6;
    cursor: pointer;
    user-select: text;
    background-color: var(--art-gray-100);
    border-radius: 6px;
  }
</style>
