<!--
  OH-UI.10 ATT&CK 技战术映射视图

  消费 OH-4.4 GET /alerts/{id}/attack-chain。
  设计：
  - 左侧告警列表（近期告警，点选即查链条）；支持手输告警 ID
  - 右侧攻击链四段：告警 → 技战术（按 tactic 分组卡片）→ 资产 → 业务系统
  - mapped=false 时如实展示「未映射」，不伪造技战术
-->
<template>
  <div class="ac-page art-full-height">
    <ElCard shadow="never" class="left-card">
      <template #header>
        <div class="card-head">
          <span class="t">选择告警</span>
          <ElButton :icon="Refresh" circle size="small" @click="loadAlerts" />
        </div>
      </template>
      <div class="id-input">
        <ElInput
          v-model="manualId"
          placeholder="或直接输入告警 ID"
          size="small"
          clearable
          @keyup.enter="loadChain(manualId.trim())"
        >
          <template #append>
            <ElButton @click="loadChain(manualId.trim())">查询</ElButton>
          </template>
        </ElInput>
      </div>
      <div v-loading="alertsLoading" class="alert-list">
        <div
          v-for="a in alerts"
          :key="a.id"
          class="alert-item"
          :class="{ active: a.id === currentId }"
          @click="loadChain(a.id)"
        >
          <div class="ai-main">{{ a.rule?.description || a.rule?.id || a.id }}</div>
          <div class="ai-sub">
            <ElTag :type="levelTag(a.rule?.level)" size="small" effect="plain">
              L{{ a.rule?.level ?? '?' }}
            </ElTag>
            {{ a.agent?.name || a.agent?.ip || '—' }}
          </div>
        </div>
        <div v-if="!alertsLoading && !alerts.length" class="empty">
          近期无告警
        </div>
      </div>
    </ElCard>

    <ElCard shadow="never" class="right-card" v-loading="chainLoading">
      <template #header>
        <div class="card-head">
          <span class="t">攻击链</span>
          <span v-if="chain" class="meta">
            告警 → 技战术 → 资产 → 业务系统
          </span>
        </div>
      </template>

      <template v-if="!chain">
        <ElEmpty description="从左侧选择一条告警查看 ATT&CK 映射" />
      </template>
      <template v-else>
        <!-- ① 告警 -->
        <div class="chain-block">
          <div class="block-title">① 告警</div>
          <ElDescriptions :column="3" border size="small">
            <ElDescriptionsItem label="规则">
              {{ chain.alert.rule_id || '—' }}（L{{ chain.alert.rule_level ?? '?' }}）
            </ElDescriptionsItem>
            <ElDescriptionsItem label="描述" :span="2">
              {{ chain.alert.rule_description || '—' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="Agent">
              {{ chain.alert.agent.name || '—' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="IP">
              {{ chain.alert.agent.ip || '—' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="时间">
              {{ formatTime(chain.alert.timestamp) }}
            </ElDescriptionsItem>
          </ElDescriptions>
        </div>

        <!-- ② 技战术 -->
        <div class="chain-block">
          <div class="block-title">
            ② ATT&CK 技战术
            <ElTag v-if="!chain.mapped" size="small" type="info">
              未映射（规则不在种子目录中）
            </ElTag>
          </div>
          <template v-if="chain.mapped">
            <div
              v-for="(techs, tactic) in groupedTechniques"
              :key="tactic"
              class="tactic-group"
            >
              <div class="tactic-name">{{ tacticLabel(String(tactic)) }}</div>
              <div class="tech-cards">
                <a
                  v-for="t in techs"
                  :key="t.technique_id"
                  :href="t.url || '#'"
                  target="_blank"
                  rel="noopener"
                  class="tech-card"
                >
                  <div class="tc-id">{{ t.technique_id }}</div>
                  <div class="tc-name">{{ t.name }}</div>
                  <div class="tc-conf">
                    <ElTag
                      size="small"
                      :type="t.confidence >= 0.9 ? 'success' : 'warning'"
                      effect="plain"
                    >
                      {{ t.confidence >= 0.9 ? '精确匹配' : '组匹配' }}
                    </ElTag>
                  </div>
                </a>
              </div>
            </div>
          </template>
          <ElAlert
            v-else
            :closable="false"
            type="info"
            show-icon
            title="该告警规则未映射到任何技战术——不代表无风险，只是目录未覆盖"
          />
        </div>

        <!-- ③ 资产 -->
        <div class="chain-block">
          <div class="block-title">③ 关联资产</div>
          <template v-if="chain.linked_asset">
            <ElDescriptions :column="3" border size="small">
              <ElDescriptionsItem label="名称">
                {{ chain.linked_asset.name || '—' }}
              </ElDescriptionsItem>
              <ElDescriptionsItem label="IP">
                {{ chain.linked_asset.asset_ip || chain.linked_asset.ip || '—' }}
              </ElDescriptionsItem>
              <ElDescriptionsItem label="类型">
                {{ chain.linked_asset.asset_type || '—' }}
              </ElDescriptionsItem>
            </ElDescriptions>
          </template>
          <ElAlert
            v-else
            :closable="false"
            type="warning"
            show-icon
            title="未锚定到台账资产（agent 不在册或 IP 未匹配）"
          />
        </div>

        <!-- ④ 业务系统 -->
        <div class="chain-block">
          <div class="block-title">④ 所属业务系统</div>
          <template v-if="chain.business_systems?.length">
            <ElTag
              v-for="bs in chain.business_systems"
              :key="bs.id"
              class="bs-tag"
              effect="plain"
            >
              {{ bs.name }}（{{ bs.protection_level || '未定级' }}
              <template v-if="bs.role">· {{ bs.role }}</template>）
            </ElTag>
          </template>
          <span v-else class="muted">该资产未挂业务系统</span>
        </div>
      </template>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { ElMessage } from 'element-plus'
  import { Refresh } from '@element-plus/icons-vue'
  import {
    getAlertAttackChain,
    getAlertList,
    type AlertItem,
    type AttackTechnique,
    type AttackChainResult
  } from '@/api/alert'

  defineOptions({ name: 'AttackChainView' })

  const alerts = ref<Array<AlertItem & { id: string }>>([])
  const alertsLoading = ref(false)
  const manualId = ref('')
  const currentId = ref('')
  const chain = ref<AttackChainResult | null>(null)
  const chainLoading = ref(false)

  const TACTIC_LABELS: Record<string, string> = {
    TA0001: '初始访问 Initial Access',
    TA0002: '执行 Execution',
    TA0003: '持久化 Persistence',
    TA0004: '权限提升 Privilege Escalation',
    TA0005: '防御绕过 Defense Evasion',
    TA0006: '凭据访问 Credential Access',
    TA0007: '发现 Discovery',
    TA0008: '横向移动 Lateral Movement',
    TA0043: '侦察 Reconnaissance'
  }
  const tacticLabel = (t: string) => TACTIC_LABELS[t] || t

  const groupedTechniques = computed(() => {
    const g: Record<string, AttackTechnique[]> = {}
    for (const t of chain.value?.techniques || []) {
      ;(g[t.tactic] = g[t.tactic] || []).push(t)
    }
    return g
  })

  const levelTag = (level?: number): 'danger' | 'warning' | 'info' => {
    if ((level ?? 0) >= 12) return 'danger'
    if ((level ?? 0) >= 7) return 'warning'
    return 'info'
  }

  const formatTime = (v?: string | null) => {
    if (!v) return '—'
    const d = new Date(v)
    return Number.isNaN(d.getTime())
      ? String(v)
      : d.toLocaleString('zh-CN', { hour12: false })
  }

  const loadAlerts = async () => {
    alertsLoading.value = true
    try {
      const res = await getAlertList({ page: 1, page_size: 30 })
      alerts.value = (res?.data?.items || []) as any
    } catch (e: any) {
      ElMessage.error(e?.message || '加载告警列表失败')
    } finally {
      alertsLoading.value = false
    }
  }

  const loadChain = async (alertId: string) => {
    if (!alertId) {
      ElMessage.warning('请输入告警 ID')
      return
    }
    currentId.value = alertId
    chainLoading.value = true
    try {
      const res = await getAlertAttackChain(alertId)
      chain.value = res?.data || null
    } catch (e: any) {
      ElMessage.error(e?.message || '加载攻击链失败')
      chain.value = null
    } finally {
      chainLoading.value = false
    }
  }

  loadAlerts()
</script>

<style lang="scss" scoped>
  .ac-page {
    display: flex;
    gap: 14px;
    height: auto;
    min-height: var(--art-full-height);

    .left-card {
      width: 320px;
      flex-shrink: 0;

      .card-head {
        display: flex;
        align-items: center;
        justify-content: space-between;

        .t {
          font-size: 15px;
          font-weight: 600;
        }
      }

      .id-input {
        margin-bottom: 10px;
      }

      .alert-list {
        max-height: calc(100vh - 260px);
        overflow-y: auto;

        .alert-item {
          padding: 8px 10px;
          margin-bottom: 6px;
          cursor: pointer;
          border: 1px solid var(--art-border-color);
          border-radius: 6px;
          transition: all 0.2s;

          &:hover {
            border-color: var(--el-color-primary);
          }

          &.active {
            background: var(--el-color-primary-light-9);
            border-color: var(--el-color-primary);
          }

          .ai-main {
            font-size: 13px;
            font-weight: 500;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }

          .ai-sub {
            display: flex;
            gap: 6px;
            align-items: center;
            margin-top: 4px;
            font-size: 12px;
            color: var(--art-text-gray-500);
          }
        }

        .empty {
          padding: 24px 0;
          font-size: 13px;
          color: var(--art-text-gray-400);
          text-align: center;
        }
      }
    }

    .right-card {
      flex: 1;

      .card-head {
        display: flex;
        gap: 10px;
        align-items: center;

        .t {
          font-size: 15px;
          font-weight: 600;
        }

        .meta {
          font-size: 12px;
          color: var(--art-text-gray-600);
        }
      }

      .chain-block {
        margin-bottom: 22px;

        .block-title {
          display: flex;
          gap: 8px;
          align-items: center;
          margin-bottom: 8px;
          font-size: 13px;
          font-weight: 600;
        }
      }

      .tactic-group {
        margin-bottom: 12px;

        .tactic-name {
          margin-bottom: 6px;
          font-size: 12px;
          color: var(--art-text-gray-600);
        }

        .tech-cards {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .tech-card {
          display: block;
          width: 200px;
          padding: 8px 10px;
          color: inherit;
          text-decoration: none;
          border: 1px solid var(--art-border-color);
          border-radius: 6px;
          transition: all 0.2s;

          &:hover {
            border-color: var(--el-color-primary);
            box-shadow: 0 1px 6px rgb(0 0 0 / 10%);
          }

          .tc-id {
            font-family: monospace;
            font-size: 12px;
            color: var(--el-color-primary);
          }

          .tc-name {
            margin: 2px 0 4px;
            font-size: 13px;
            font-weight: 500;
          }
        }
      }

      .bs-tag {
        margin-right: 6px;
      }

      .muted {
        font-size: 13px;
        color: var(--art-text-gray-400);
      }
    }
  }
</style>
