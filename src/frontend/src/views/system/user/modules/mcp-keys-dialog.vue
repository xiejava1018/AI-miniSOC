<!-- admin 侧：用户 MCP Key 监管对话框（仅 admin 可见）
     - 只读 Key 列表
     - 代发新 Key（一次性明文弹窗——admin 需自行转交用户，本系统永不落库/落日志）
     - 强制注销（带名称二次确认）
     - admin 任何情况下都看不到既有 Key 明文（库内只存 hash） -->
<template>
  <ElDialog
    v-model="visible"
    :title="title"
    width="760px"
    align-center
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <ElAlert type="warning" :closable="false" class="mb-3">
      admin 可代发 / 强制注销该用户的 MCP Key。<b>明文仅申请时返回一次</b>，请立刻转交用户；本系统不存储明文。
    </ElAlert>

    <div class="flex-c justify-between mb-3">
      <span class="text-sm text-g-600">Key 列表（{{ keys.length }}）</span>
      <ElButton type="primary" size="small" @click="openCreateDialog">
        <ArtSvgIcon icon="ri:add-line" class="mr-1" />代发新 Key
      </ElButton>
    </div>

    <ElTable v-if="keys.length" :data="keys" border size="small" v-loading="loading">
      <ElTableColumn label="名称" prop="name" min-width="120" />
      <ElTableColumn label="前缀" min-width="130">
        <template #default="{ row }">
          <code class="text-xs">{{ row.key_prefix }}…</code>
        </template>
      </ElTableColumn>
      <ElTableColumn label="状态" width="120">
        <template #default="{ row }">
          <ElTag v-if="row.status === 'active' && (row.days_remaining ?? 0) > 0"
                 :type="(row.days_remaining ?? 99) <= 7 ? 'warning' : 'success'" size="small">
            活跃 · 剩 {{ row.days_remaining }} 天
          </ElTag>
          <ElTag v-else-if="row.status === 'active'" type="info" size="small">已过期</ElTag>
          <ElTag v-else type="danger" size="small">已注销</ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="最后使用" min-width="150">
        <template #default="{ row }">{{ row.last_used_at ? formatTime(row.last_used_at) : '从未' }}</template>
      </ElTableColumn>
      <ElTableColumn label="到期" min-width="150">
        <template #default="{ row }">{{ row.expires_at ? formatTime(row.expires_at) : '—' }}</template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <ElButton v-if="row.status === 'active'" link type="danger" size="small" @click="confirmRevoke(row)">
            强制注销
          </ElButton>
          <ElButton v-else-if="row.status === 'revoked'" link type="danger" size="small" @click="confirmPurge(row)">
            彻底删除
          </ElButton>
          <span v-else class="text-g-500 text-xs">—</span>
        </template>
      </ElTableColumn>
    </ElTable>
    <ElEmpty v-else description="该用户尚未申请 MCP Key" :image-size="80" />

    <!-- 代发新 Key 弹窗 -->
    <ElDialog
      v-model="createDialogVisible"
      title="代发新 Key"
      width="480px"
      align-center
      :close-on-click-modal="false"
      append-to-body
    >
      <ElForm ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <ElFormItem label="名称" prop="name">
          <ElInput v-model="createForm.name" placeholder="例如 workbuddy" maxlength="50" show-word-limit />
        </ElFormItem>
        <ElFormItem label="有效期" prop="validity_days">
          <ElSelect v-model="createForm.validity_days" style="width: 100%">
            <ElOption :value="7" label="7 天" />
            <ElOption :value="30" label="30 天" />
            <ElOption :value="90" label="90 天" />
            <ElOption :value="365" label="365 天（上限）" />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="creating" @click="submitCreate">代发</ElButton>
      </template>
    </ElDialog>

    <!-- 一次性明文展示（仅代发成功后显示一次） -->
    <ElDialog v-model="plaintextVisible" title="代发成功 — 请立即转交用户" width="560px" align-center append-to-body>
      <ElAlert type="error" :closable="false" class="mb-3">
        此明文仅显示一次，关闭后无法再次查看。admin 需自行转交给用户并建议用户修改 Key 名称。
      </ElAlert>
      <div class="bg-g-100 p-3 rounded font-mono text-sm break-all mb-2" data-test="plaintext-key">
        {{ createdPlaintext }}
      </div>
      <ElButton type="primary" plain @click="copyPlaintext">
        <ArtSvgIcon icon="ri:file-copy-line" class="mr-1" />一键复制
      </ElButton>
      <template #footer>
        <ElButton type="primary" @click="plaintextVisible = false">我已转交，关闭</ElButton>
      </template>
    </ElDialog>
  </ElDialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  fetchGetUserMcpKeys,
  fetchAdminCreateMcpKey,
  fetchAdminRevokeMcpKey,
  fetchAdminPurgeMcpKey,
  type McpKeyItem
} from '@/api/user-center'

const props = defineProps<{ modelValue: boolean; userId: number; username: string }>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean] }>()

const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })
const title = computed(() => `用户 ${props.username} 的 MCP Key`)

const keys = ref<McpKeyItem[]>([])
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    keys.value = (await fetchGetUserMcpKeys(props.userId)) || []
  } finally {
    loading.value = false
  }
}
watch(visible, async (v) => { if (v) await load() })

// 代发
const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const creating = ref(false)
const createForm = reactive({ name: '', validity_days: 90 })
const createRules: FormRules = {
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { min: 1, max: 50, message: '长度 1-50', trigger: 'blur' }
  ],
  validity_days: [{ required: true, message: '请选择有效期', trigger: 'change' }]
}
const openCreateDialog = () => { createForm.name = ''; createDialogVisible.value = true }
const submitCreate = async () => {
  if (!createFormRef.value) return
  await createFormRef.value.validate()
  creating.value = true
  try {
    const created = await fetchAdminCreateMcpKey(props.userId, { ...createForm })
    createdPlaintext.value = created.key
    createDialogVisible.value = false
    plaintextVisible.value = true
    ElMessage.success(`已代发 Key "${created.name}"`)
    await load()
  } finally {
    creating.value = false
  }
}

// 一次性明文
const plaintextVisible = ref(false)
const createdPlaintext = ref('')
const copyPlaintext = async () => {
  try { await navigator.clipboard.writeText(createdPlaintext.value); ElMessage.success('已复制到剪贴板') }
  catch { ElMessage.error('复制失败，请手动选中') }
}

// 强制注销
const confirmRevoke = async (row: McpKeyItem) => {
  try {
    await ElMessageBox.confirm(
      `强制注销用户 "${props.username}" 的 Key "${row.name}"（前缀 ${row.key_prefix}）？此操作即时生效。`,
      '强制注销',
      { type: 'warning', confirmButtonText: '确认注销', cancelButtonText: '取消' }
    )
  } catch { return }
  await fetchAdminRevokeMcpKey(props.userId, row.id)
  ElMessage.success('已强制注销')
  await load()
}

// 彻底删除已注销 Key
const confirmPurge = async (row: McpKeyItem) => {
  try {
    await ElMessageBox.confirm(
      `彻底删除用户 "${props.username}" 的 Key "${row.name}"（前缀 ${row.key_prefix}）？\n\n` +
      `该记录将被物理删除，仅审计哈希链留痕，不可恢复。`,
      '彻底删除',
      { type: 'warning', confirmButtonText: '确认彻底删除', cancelButtonText: '取消' }
    )
  } catch { return }
  await fetchAdminPurgeMcpKey(props.userId, row.id)
  ElMessage.success('已彻底删除')
  await load()
}

const formatTime = (iso: string) => { try { return new Date(iso).toLocaleString('zh-CN') } catch { return iso } }
const handleClose = () => { visible.value = false }
</script>
