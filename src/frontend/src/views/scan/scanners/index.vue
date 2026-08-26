<!--
  资产扫描 - 扫描器管理（admin only）

  - 扫描器列表（名称/IP/状态/能力/最后心跳）
  - 注册新扫描器：返回明文 API Key，仅此一次显示，可复制
  - 编辑（名称/IP/能力/可达网段）、轮换 Key、注销
-->
<template>
  <div class="scanners-page art-full-height">
    <ElCard shadow="never" class="page-card">
      <template #header>
        <div class="card-header">
          <span class="title">扫描器</span>
          <div class="actions">
            <ElButton :loading="loading" @click="loadAgents">刷新</ElButton>
            <ElButton
              v-if="hasAuth('scanner_manage')"
              type="primary"
              @click="openRegister"
            >
              注册扫描器
            </ElButton>
          </div>
        </div>
      </template>

      <ElTable v-loading="loading" :data="agents" stripe style="width: 100%">
        <ElTableColumn prop="name" label="名称" min-width="140" />
        <ElTableColumn prop="ip" label="IP" min-width="130">
          <template #default="{ row }">{{ row.ip || '—' }}</template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="100">
          <template #default="{ row }">
            <ElTag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="能力" min-width="160">
          <template #default="{ row }">
            <ElTag
              v-for="c in row.capabilities"
              :key="c"
              size="small"
              effect="plain"
              class="cap-tag"
            >
              {{ c }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="可达网段" min-width="180">
          <template #default="{ row }">
            <span v-if="row.reachable_subnets?.length">
              {{ row.reachable_subnets.join(', ') }}
            </span>
            <span v-else class="muted">—</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="最后心跳" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.last_heartbeat) || '从未' }}
          </template>
        </ElTableColumn>
        <ElTableColumn prop="created_by" label="创建人" width="110">
          <template #default="{ row }">{{ row.created_by || '—' }}</template>
        </ElTableColumn>
        <ElTableColumn v-if="hasAuth('scanner_manage')" label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <ElButton link type="primary" size="small" @click="openEdit(row)">编辑</ElButton>
            <ElButton link type="warning" size="small" @click="rotateKey(row)">轮换Key</ElButton>
            <ElPopconfirm
              title="注销后该扫描器将无法再连接，确认？"
              @confirm="removeAgent(row)"
            >
              <template #reference>
                <ElButton link type="danger" size="small">注销</ElButton>
              </template>
            </ElPopconfirm>
          </template>
        </ElTableColumn>
      </ElTable>
    </ElCard>

    <!-- 注册 / 编辑弹窗 -->
    <ElDialog
      v-model="formVisible"
      :title="editing ? '编辑扫描器' : '注册扫描器'"
      width="520px"
    >
      <ElForm :model="form" label-width="100px">
        <ElFormItem label="名称" required>
          <ElInput v-model="form.name" placeholder="如 kali-45" />
        </ElFormItem>
        <ElFormItem label="IP">
          <ElInput v-model="form.ip" placeholder="如 192.168.0.45" />
        </ElFormItem>
        <ElFormItem label="能力">
          <ElSelect v-model="form.capabilities" multiple placeholder="选择能力" style="width:100%">
            <ElOption label="public（公网端口扫描）" value="public" />
            <ElOption label="internal（内网发现）" value="internal" />
            <ElOption label="ports（端口扫描）" value="ports" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="可达网段">
          <ElInput
            v-model="subnetsText"
            placeholder="逗号分隔，如 192.168.0.0/24,10.0.0.0/16"
          />
        </ElFormItem>
        <ElFormItem v-if="editing" label="启用">
          <ElSwitch v-model="form.enabled" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="formVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="submitForm">
          {{ editing ? '保存' : '注册' }}
        </ElButton>
      </template>
    </ElDialog>

    <!-- 注册成功：明文 Key 仅此一次 -->
    <ElDialog v-model="keyVisible" title="扫描器注册成功" width="560px">
      <ElAlert
        type="warning"
        :closable="false"
        show-icon
        title="请立即复制并妥善保存 API Key"
        description="该明文 Key 仅显示一次，关闭后无法再查看。"
        class="key-alert"
      />
      <div class="key-box">
        <span class="key-text">{{ createdKey }}</span>
        <ElButton type="primary" size="small" @click="copyKey">复制</ElButton>
      </div>
      <div class="key-hint">
        scanner_id：<code>{{ createdAgent?.scanner_id }}</code>
      </div>
      <template #footer>
        <ElButton type="primary" @click="keyVisible = false">我已保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, onMounted } from 'vue'
  import { ElMessage } from 'element-plus'
  import { useAuth } from '@/hooks/core/useAuth'
  import {
    getScannerAgents,
    registerScannerAgent,
    updateScannerAgent,
    deleteScannerAgent,
    type ScannerAgent
  } from '@/api/scan'

  defineOptions({ name: 'ScanScanners' })

  const { hasAuth } = useAuth()

  const agents = ref<ScannerAgent[]>([])
  const loading = ref(false)

  const formVisible = ref(false)
  const saving = ref(false)
  const editing = ref<ScannerAgent | null>(null)
  const form = ref({
    name: '',
    ip: '',
    capabilities: ['public'] as string[],
    enabled: true
  })
  const subnetsText = ref('')

  const keyVisible = ref(false)
  const createdKey = ref('')
  const createdAgent = ref<ScannerAgent | null>(null)

  const statusType = (s: string) =>
    ({ online: 'success', offline: 'danger', unknown: 'info', disabled: 'info' }[s] || 'info')
  const statusLabel = (s: string) =>
    ({ online: '在线', offline: '离线', unknown: '未知', disabled: '已停用' }[s] || s)

  const formatTime = (t?: string | null) => {
    if (!t) return ''
    try {
      return new Date(t).toLocaleString('zh-CN', { hour12: false })
    } catch {
      return t
    }
  }

  const loadAgents = async () => {
    loading.value = true
    try {
      const res = await getScannerAgents()
      agents.value = res.items || []
    } catch (e: any) {
      ElMessage.error(e?.message || '加载扫描器列表失败')
    } finally {
      loading.value = false
    }
  }

  const resetForm = () => {
    form.value = { name: '', ip: '', capabilities: ['public'], enabled: true }
    subnetsText.value = ''
    editing.value = null
  }

  const openRegister = () => {
    resetForm()
    formVisible.value = true
  }

  const openEdit = (row: ScannerAgent) => {
    editing.value = row
    form.value = {
      name: row.name,
      ip: row.ip || '',
      capabilities: [...(row.capabilities || [])],
      enabled: row.enabled
    }
    subnetsText.value = (row.reachable_subnets || []).join(',')
    formVisible.value = true
  }

  const submitForm = async () => {
    if (!form.value.name.trim()) {
      ElMessage.warning('请输入名称')
      return
    }
    saving.value = true
    try {
      const subnets = subnetsText.value
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      if (editing.value) {
        await updateScannerAgent(editing.value.scanner_id, {
          name: form.value.name,
          ip: form.value.ip || undefined,
          capabilities: form.value.capabilities,
          reachable_subnets: subnets,
          enabled: form.value.enabled
        })
        ElMessage.success('已保存')
        formVisible.value = false
      } else {
        const res = await registerScannerAgent({
          name: form.value.name,
          ip: form.value.ip || undefined,
          capabilities: form.value.capabilities,
          reachable_subnets: subnets
        })
        createdKey.value = res.api_key || ''
        createdAgent.value = res
        formVisible.value = false
        keyVisible.value = true
      }
      loadAgents()
    } catch (e: any) {
      ElMessage.error(e?.message || '保存失败')
    } finally {
      saving.value = false
    }
  }

  const rotateKey = async (row: ScannerAgent) => {
    try {
      const res = await updateScannerAgent(row.scanner_id, { rotate_key: true })
      if (res.api_key) {
        createdKey.value = res.api_key
        createdAgent.value = res
        keyVisible.value = true
      } else {
        ElMessage.success('Key 已轮换')
      }
      loadAgents()
    } catch (e: any) {
      ElMessage.error(e?.message || '轮换失败')
    }
  }

  const removeAgent = async (row: ScannerAgent) => {
    try {
      await deleteScannerAgent(row.scanner_id)
      ElMessage.success('已注销')
      loadAgents()
    } catch (e: any) {
      ElMessage.error(e?.message || '注销失败')
    }
  }

  const copyKey = async () => {
    try {
      await navigator.clipboard.writeText(createdKey.value)
      ElMessage.success('已复制到剪贴板')
    } catch {
      ElMessage.warning('复制失败，请手动选择文本')
    }
  }

  onMounted(loadAgents)
</script>

<style lang="scss" scoped>
  .scanners-page {
    padding: 12px;
  }
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    .title {
      font-weight: 600;
      font-size: 15px;
    }
  }
  .cap-tag {
    margin-right: 4px;
  }
  .muted {
    color: var(--el-text-color-placeholder);
  }
  .key-alert {
    margin-bottom: 12px;
  }
  .key-box {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: var(--el-fill-color-light);
    border-radius: 6px;
    .key-text {
      flex: 1;
      font-family: monospace;
      word-break: break-all;
    }
  }
  .key-hint {
    margin-top: 10px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    code {
      font-family: monospace;
    }
  }
</style>
