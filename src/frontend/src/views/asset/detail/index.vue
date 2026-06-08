<template>
  <div class="asset-detail-page art-full-height">
    <!-- 顶部返回栏 -->
    <div class="detail-header">
      <ElButton @click="goBack" :icon="ArrowLeft" text>返回列表</ElButton>
    </div>

    <!-- 资产基本信息卡片 -->
    <ElCard shadow="never" class="info-card" v-loading="detailLoading">
      <template #header>
        <div class="card-header">
          <span class="title">{{ assetDetail.name || assetDetail.asset_ip || '资产详情' }}</span>
          <div class="header-tags">
            <ElTag v-if="assetDetail.asset_status" :type="statusTagType" effect="dark" size="small">
              {{ statusLabelMap[assetDetail.asset_status] || assetDetail.asset_status || '--' }}
            </ElTag>
            <ElTag v-if="assetDetail.criticality" :type="criticalityTagType" effect="plain" size="small">
              {{ criticalityLabelMap[assetDetail.criticality] || assetDetail.criticality || '--' }}
            </ElTag>
            <ElTag v-if="assetDetail.data_source" type="info" effect="plain" size="small">
              {{ dataSourceLabelMap[assetDetail.data_source] || assetDetail.data_source || '--' }}
            </ElTag>
          </div>
        </div>
      </template>

      <ElDescriptions :column="3" border>
        <ElDescriptionsItem label="IP地址">{{ assetDetail.asset_ip || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="资产名称">{{ assetDetail.name || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="资产类型">{{ assetTypeLabelMap[assetDetail.asset_type] || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="网络段">{{ assetDetail.network_segment || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="网络区域">{{ networkZoneLabelMap[assetDetail.network_zone] || assetDetail.network_zone || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="MAC地址">{{ assetDetail.mac_address || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="负责人">{{ assetDetail.owner || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="负责人电话">{{ assetDetail.owner_contact || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="数据分类">
          <ElTag v-if="assetDetail.data_classification" type="warning" effect="plain" size="small">
            {{ dataClassLabelMap[assetDetail.data_classification] || assetDetail.data_classification }}
          </ElTag>
          <span v-else>--</span>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="业务单元">{{ assetDetail.business_unit || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="操作系统">
          {{ assetDetail.os_name ? `${assetDetail.os_name} ${assetDetail.os_version || ''}`.trim() : '--' }}
        </ElDescriptionsItem>
        <ElDescriptionsItem label="Wazuh Agent">{{ assetDetail.wazuh_agent_id || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="创建时间">{{ formatTime(assetDetail.created_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="更新时间">{{ formatTime(assetDetail.updated_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="状态更新">{{ formatTime(assetDetail.status_updated_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="描述" :span="3">{{ assetDetail.asset_description || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="标签" :span="3">
          <ElTag
            v-for="tag in tagsData"
            :key="tag.id"
            type="info"
            effect="light"
            class="mr-1 mb-1"
            closable
            @close="handleDeleteTag(tag)"
          >
            {{ tag.tag_key }}: {{ tag.tag_value }}
          </ElTag>
          <ElButton size="small" type="primary" plain @click="showTagDialog('add')">
            <ElIcon><Plus /></ElIcon>添加标签
          </ElButton>
        </ElDescriptionsItem>
      </ElDescriptions>
    </ElCard>

    <!-- 安全摘要卡(详情页 v2 新增) -->
    <ElCard shadow="never" class="summary-card" v-loading="summaryLoading">
      <template #header>
        <div class="card-header">
          <span class="title">安全摘要</span>
          <ElButton size="small" text :icon="Refresh" @click="loadSummary" :loading="summaryLoading">刷新</ElButton>
        </div>
      </template>

      <div class="summary-grid">
        <MetricCard
          label="24h 告警"
          :value="summary.alert_24h"
          type="danger"
          :clickable="summary.alert_24h > 0"
          @click="activeTab = 'alerts'"
          :sub-label="summary.alert_critical_24h > 0 ? `高危 ${summary.alert_critical_24h}` : '无高危'"
        />
        <MetricCard
          label="高危 CVE"
          :value="summary.vuln_critical"
          type="danger"
          :clickable="summary.vuln_critical > 0"
          @click="activeTab = 'vulnerabilities'"
          :sub-label="`未修复 ${summary.vuln_total} 个`"
        />
        <MetricCard
          label="开放端口"
          :value="summary.open_ports"
          :type="summary.high_risk_ports > 0 ? 'warning' : 'info'"
          :clickable="true"
          @click="activeTab = 'ports'"
          :sub-label="summary.high_risk_ports > 0 ? `高危 ${summary.high_risk_ports}` : '无高危'"
        />
        <MetricCard
          label="应用数"
          :value="summary.applications"
          type="info"
          :clickable="false"
          sub-label="Wazuh packages"
        />
        <MetricCard
          label="SCA 合规率"
          :value="summary.sca_pass_rate !== null ? Math.round(summary.sca_pass_rate * 100) : '-'"
          :type="scaPassRateType"
          :clickable="false"
          :suffix="summary.sca_pass_rate !== null ? '%' : ''"
          :sub-label="summary.sca_total > 0 ? `失败 ${summary.sca_failed}/${summary.sca_total}` : '待接入'"
        />
        <MetricCard
          label="在线状态"
          :value="onlineStatusLabel"
          :type="onlineStatusType"
          :clickable="false"
          :sub-label="summary.last_port_scan ? `端口扫描 ${relativeTime.format(summary.last_port_scan)}` : '尚无扫描'"
        />
      </div>
    </ElCard>

    <!-- Tab 区域 -->
    <ElCard shadow="never" class="tab-card">
      <ElTabs v-model="activeTab">
        <!-- 1. 应用清单(Phase 2 接入) -->
        <ElTabPane label="应用清单" name="applications">
          <ElEmpty description="应用清单数据待 Phase 2 接入 Wazuh 同步服务后填充">
            <template #image>
              <ElIcon :size="48" color="#909399"><Box /></ElIcon>
            </template>
          </ElEmpty>
        </ElTabPane>

        <!-- 2. 漏洞(Phase 2 接入) -->
        <ElTabPane label="漏洞" name="vulnerabilities">
          <ElEmpty description="漏洞数据待 Phase 2 接入 Wazuh 漏洞缓存表后填充">
            <template #image>
              <ElIcon :size="48" color="#909399"><Warning /></ElIcon>
            </template>
          </ElEmpty>
        </ElTabPane>

        <!-- 3. 端口管理(现有,增强) -->
        <ElTabPane label="端口" name="ports">
          <div class="tab-header">
            <ElButton type="primary" size="small" @click="showPortDialog">添加端口</ElButton>
          </div>
          <ElTable :data="portsData" v-loading="portsLoading" border stripe style="width: 100%">
            <ElTableColumn prop="port" label="端口" width="80" align="center">
              <template #default="{ row }">
                <span :class="{ 'high-risk-port': isHighRisk(row.port) }">{{ row.port }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="protocol" label="协议" width="80" align="center" />
            <ElTableColumn prop="state" label="状态" width="90" align="center">
              <template #default="{ row }">
                <ElTag :type="row.state === 'open' ? 'success' : row.state === 'closed' ? 'danger' : 'warning'" size="small" effect="light">
                  {{ row.state || '--' }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="service" label="服务" width="120" align="center" />
            <ElTableColumn prop="version" label="版本" min-width="140" align="center" />
            <ElTableColumn label="风险等级" width="180" align="center">
              <template #default="{ row }">
                <ElTag v-if="isHighRisk(row.port)" :type="riskTagType(row.port)" size="small" effect="dark">
                  {{ riskLabel(row.port) }}
                </ElTag>
                <span v-else class="text-placeholder">--</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="漏洞" min-width="180" align="center">
              <template #default="{ row }">
                <ElTag
                  v-for="(vuln, idx) in parseVulns(row.vulnerability)"
                  :key="idx"
                  type="danger"
                  size="small"
                  effect="plain"
                  class="mr-1 mb-1"
                >
                  {{ vuln }}
                </ElTag>
                <span v-if="!row.vulnerability" class="text-placeholder">--</span>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="scan_time" label="扫描时间" width="170" align="center">
              <template #default="{ row }">
                <span :title="formatTime(row.scan_time)">{{ relativeTime.format(row.scan_time) }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="操作" width="100" align="center" fixed="right">
              <template #default="{ row }">
                <ElButton type="danger" link size="small" @click="handleDeletePort(row)">删除</ElButton>
              </template>
            </ElTableColumn>
          </ElTable>
          <ElEmpty v-if="!portsLoading && portsData.length === 0" description="暂无端口数据" />
        </ElTabPane>

        <!-- 4. 基线(Phase 4 接入) -->
        <ElTabPane label="基线" name="baseline">
          <ElEmpty description="SCA 基线数据待 Phase 4 接入 Wazuh SCA 缓存表后填充">
            <template #image>
              <ElIcon :size="48" color="#909399"><Document /></ElIcon>
            </template>
          </ElEmpty>
        </ElTabPane>

        <!-- 5. 告警 -->
        <ElTabPane label="告警" name="alerts">
          <div class="tab-header">
            <ElButton type="primary" size="small" :icon="Refresh" @click="loadAlerts" :loading="alertsLoading">刷新</ElButton>
          </div>
          <ElTable :data="alertsData" v-loading="alertsLoading" border stripe style="width: 100%">
            <ElTableColumn label="时间" width="170" align="center">
              <template #default="{ row }">{{ formatTime(row.timestamp) }}</template>
            </ElTableColumn>
            <ElTableColumn label="等级" width="100" align="center">
              <template #default="{ row }">
                <ElTag :type="getAlertLevelType(row.rule?.level)" size="small" effect="dark">
                  L{{ row.rule?.level ?? '-' }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="rule.description" label="规则描述" min-width="280" align="left" show-overflow-tooltip />
            <ElTableColumn prop="agent.id" label="Agent" width="100" align="center" />
            <ElTableColumn prop="location" label="位置" width="120" align="center" show-overflow-tooltip />
            <ElTableColumn prop="rule.id" label="规则ID" width="100" align="center" />
          </ElTable>
          <ElEmpty v-if="!alertsLoading && alertsData.length === 0" description="暂无告警(默认查询最近 24h)" />
        </ElTabPane>

        <!-- 6. 数据来源 -->
        <ElTabPane label="数据来源" name="datasources">
          <ElTable :data="datasourcesData" v-loading="datasourcesLoading" border stripe style="width: 100%">
            <ElTableColumn prop="source" label="来源" width="160" align="center">
              <template #default="{ row }">
                <ElTag type="primary" effect="plain" size="small">
                  {{ sourceLabelMap[row.source] || row.source }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="source_id" label="来源ID" width="140" align="center" />
            <ElTableColumn prop="source_status" label="来源状态" width="120" align="center">
              <template #default="{ row }">
                <ElTag v-if="row.source_status" :type="getSourceStatusTagType(row.source_status)" size="small" effect="dark">
                  {{ statusLabelMap[row.source_status] || row.source_status }}
                </ElTag>
                <span v-else class="text-placeholder">--</span>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="last_seen_at" label="最后发现" width="170" align="center">
              <template #default="{ row }">
                <span :title="formatTime(row.last_seen_at)">{{ relativeTime.format(row.last_seen_at) }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="来源详情" min-width="280" align="left">
              <template #default="{ row }">
                <ElPopover v-if="row.source_metadata && Object.keys(row.source_metadata).length > 0" placement="left" :width="320" trigger="click">
                  <template #reference>
                    <ElButton size="small" type="info" link>查看详情 ({{ Object.keys(row.source_metadata).length }} 项)</ElButton>
                  </template>
                  <div class="source-meta-popover">
                    <div v-for="(val, key) in row.source_metadata" :key="key" class="source-meta-row">
                      <span class="source-meta-key">{{ key }}:</span>
                      <span class="source-meta-value">{{ val ?? '--' }}</span>
                    </div>
                  </div>
                </ElPopover>
                <span v-else class="text-placeholder">--</span>
              </template>
            </ElTableColumn>
          </ElTable>
          <ElEmpty v-if="!datasourcesLoading && datasourcesData.length === 0" description="暂无数据来源记录" />
        </ElTabPane>
      </ElTabs>
    </ElCard>

    <!-- 端口弹窗 -->
    <ElDialog v-model="portDialogVisible" title="添加端口" width="450px" align-center :close-on-click-modal="false">
      <ElForm ref="portFormRef" :model="portFormData" :rules="portRules" label-width="80px">
        <ElFormItem label="端口" prop="port">
          <ElInputNumber v-model="portFormData.port" :min="1" :max="65535" style="width: 100%" />
        </ElFormItem>
        <ElFormItem label="协议" prop="protocol">
          <ElSelect v-model="portFormData.protocol" style="width: 100%">
            <ElOption label="TCP" value="tcp" />
            <ElOption label="UDP" value="udp" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="状态" prop="state">
          <ElSelect v-model="portFormData.state" style="width: 100%">
            <ElOption label="开放" value="open" />
            <ElOption label="关闭" value="closed" />
            <ElOption label="过滤" value="filtered" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="服务" prop="service">
          <ElInput v-model="portFormData.service" placeholder="如: ssh, http, mysql" />
        </ElFormItem>
        <ElFormItem label="版本" prop="version">
          <ElInput v-model="portFormData.version" placeholder="服务版本信息" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="portDialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="handlePortSubmit">确定</ElButton>
      </template>
    </ElDialog>

    <!-- 标签弹窗(从基本信息卡触发) -->
    <ElDialog
      v-model="tagDialogVisible"
      :title="tagDialogType === 'add' ? '添加标签' : '编辑标签'"
      width="450px"
      align-center
      :close-on-click-modal="false"
    >
      <ElForm ref="tagFormRef" :model="tagFormData" :rules="tagRules" label-width="80px">
        <ElFormItem label="标签键" prop="tag_key">
          <ElSelect
            v-model="tagFormData.tag_key"
            filterable
            allow-create
            placeholder="选择或输入标签键"
            style="width: 100%"
          >
            <ElOption
              v-for="item in commonTagKeys"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="标签值" prop="tag_value">
          <ElSelect
            v-if="tagKeyOptions.length > 0"
            v-model="tagFormData.tag_value"
            filterable
            allow-create
            placeholder="选择或输入标签值"
            style="width: 100%"
          >
            <ElOption
              v-for="opt in tagKeyOptions"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </ElSelect>
          <ElInput v-else v-model="tagFormData.tag_value" placeholder="请输入标签值" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="tagDialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="handleTagSubmit">确定</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted, nextTick } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { ArrowLeft, Refresh, Plus, Box, Warning, Document } from '@element-plus/icons-vue'
  import { FormInstance, ElMessageBox, ElMessage } from 'element-plus'
  import {
    getAssetDetail,
    getAssetPorts,
    addAssetPort,
    deleteAssetPort,
    getAssetTags,
    addAssetTag,
    deleteAssetTag,
    getCommonTagKeys,
    getAssetSummary,
    getAssetSources
  } from '@/api/asset'
  import { getAlertsByIp, getAlertsByAgentId } from '@/api/alert'
  import { useDictStore } from '@/store/modules/dict'
  import { useRelativeTime } from '@/composables/useRelativeTime'
  import { getHighRiskPort, type PortRisk } from '@/constants/highRiskPorts'
  import MetricCard from './components/MetricCard.vue'

  const route = useRoute()
  const router = useRouter()
  const assetId = computed(() => route.params.id as string)
  const dictStore = useDictStore()
  const relativeTime = useRelativeTime()

  // 字典映射
  const assetTypeLabelMap = computed(() => dictStore.getLabelMap('asset_type'))
  const criticalityLabelMap = computed(() => dictStore.getLabelMap('asset_criticality'))
  const criticalityColorMap = computed(() => dictStore.getColorMap('asset_criticality'))
  const statusLabelMap = computed(() => dictStore.getLabelMap('asset_status'))
  const statusColorMap = computed(() => dictStore.getColorMap('asset_status'))
  const networkZoneLabelMap = computed(() => dictStore.getLabelMap('network_zone'))
  const dataSourceLabelMap = computed(() => dictStore.getLabelMap('data_source'))
  const dataClassLabelMap = computed(() => dictStore.getLabelMap('data_classification'))

  // 资产详情
  const detailLoading = ref(false)
  const assetDetail = ref<any>({})
  const statusTagType = computed(() => statusColorMap.value[assetDetail.value.asset_status] as any || 'info')
  const criticalityTagType = computed(() => criticalityColorMap.value[assetDetail.value.criticality] as any || 'info')

  const loadDetail = async () => {
    if (!assetId.value) return
    detailLoading.value = true
    try {
      const res = await getAssetDetail(assetId.value)
      const r: any = res
      assetDetail.value = r?.data || r || {}
    } catch (err) {
      console.error('获取资产详情出错:', err)
      ElMessage.error('获取资产详情失败')
    } finally {
      detailLoading.value = false
    }
  }

  // Tab - 默认进 ports(Phase 1 唯一有数据的 Tab)
  // Phase 3 接入应用数据后,改回默认 applications(设计文档 §4.2)
  const activeTab = ref('ports')

  // ========== 安全摘要 ==========
  const summaryLoading = ref(false)
  const summary = ref<Api.Asset.AssetSummary>({
    asset_id: '',
    online_status: 'unknown',
    alert_24h: 0,
    alert_critical_24h: 0,
    open_incidents: 0,
    vuln_critical: 0,
    vuln_high: 0,
    vuln_total: 0,
    open_ports: 0,
    high_risk_ports: 0,
    applications: 0,
    sca_pass_rate: null,
    sca_total: 0,
    sca_failed: 0,
    last_port_scan: null,
    last_vuln_scan: null,
    last_sca_scan: null,
    data_classification: 'internal',
    owner: null,
    owner_contact: null,
    tags: []
  })

  const loadSummary = async () => {
    if (!assetId.value) return
    summaryLoading.value = true
    try {
      const res = await getAssetSummary(assetId.value)
      const r: any = res
      const d = r?.data
      if (d) {
        summary.value = { ...summary.value, ...d }
      }
    } catch (err) {
      console.error('获取安全摘要失败:', err)
    } finally {
      summaryLoading.value = false
    }
  }

  // 摘要派生
  const onlineStatusLabel = computed(() => {
    const map: Record<string, string> = {
      online: '在线',
      offline: '离线',
      unknown: '未知'
    }
    return map[summary.value.online_status] || '未知'
  })

  const onlineStatusType = computed<'success' | 'danger' | 'info'>(() => {
    if (summary.value.online_status === 'online') return 'success'
    if (summary.value.online_status === 'offline') return 'danger'
    return 'info'
  })

  const scaPassRateType = computed<'success' | 'warning' | 'danger' | 'neutral'>(() => {
    if (summary.value.sca_pass_rate === null) return 'neutral'
    if (summary.value.sca_pass_rate >= 0.9) return 'success'
    if (summary.value.sca_pass_rate >= 0.7) return 'warning'
    return 'danger'
  })

  // ========== 端口管理 ==========
  const portsLoading = ref(false)
  const portsData = ref<any[]>([])
  const portDialogVisible = ref(false)
  const portFormRef = ref<FormInstance>()
  const portFormData = reactive({
    port: 80,
    protocol: 'tcp',
    state: 'open',
    service: '',
    version: ''
  })
  const portRules = {
    port: [{ required: true, message: '请输入端口号', trigger: 'blur' }],
    protocol: [{ required: true, message: '请选择协议', trigger: 'change' }],
    state: [{ required: true, message: '请选择状态', trigger: 'change' }]
  }

  const isHighRisk = (port: number) => getHighRiskPort(port) !== null
  const riskLabel = (port: number) => getHighRiskPort(port)?.reason ?? ''
  const riskTagType = (port: number): 'danger' | 'warning' | 'info' => {
    const info = getHighRiskPort(port)
    if (!info) return 'info'
    if (info.risk === 'critical' || info.risk === 'high') return 'danger'
    return 'warning'
  }

  const parseVulns = (v?: string | null): string[] => {
    if (!v) return []
    return v
      .split(/[,;]/)
      .map((s) => s.trim())
      .filter(Boolean)
  }

  const loadPorts = async () => {
    if (!assetId.value) return
    portsLoading.value = true
    try {
      const res = await getAssetPorts(assetId.value, { page: 1, pageSize: 100 })
      const r: any = res
      const d = r?.data
      portsData.value = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : []
    } catch {
      portsData.value = []
    } finally {
      portsLoading.value = false
    }
  }

  const showPortDialog = () => {
    portDialogVisible.value = true
    portFormData.port = 80
    portFormData.protocol = 'tcp'
    portFormData.state = 'open'
    portFormData.service = ''
    portFormData.version = ''
    nextTick(() => portFormRef.value?.clearValidate())
  }

  const handlePortSubmit = async () => {
    if (!portFormRef.value) return
    await portFormRef.value.validate(async (valid) => {
      if (valid) {
        try {
          const res = await addAssetPort(assetId.value, {
            ...portFormData,
            asset_ip: assetDetail.value.asset_ip
          })
          if ((res as any)?.code === 200 || res) {
            ElMessage.success('端口添加成功')
            portDialogVisible.value = false
            loadPorts()
          } else {
            ElMessage.error((res as any)?.msg || '添加失败')
          }
        } catch (err) {
          ElMessage.error('添加端口失败')
        }
      }
    })
  }

  const handleDeletePort = (row: any) => {
    ElMessageBox.confirm(`确定删除端口 ${row.port}/${row.protocol}？`, '删除端口', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
      .then(async () => {
        try {
          await deleteAssetPort(row.id)
          ElMessage.success('删除成功')
          loadPorts()
        } catch {
          ElMessage.error('删除失败')
        }
      })
      .catch(() => {})
  }

  // ========== 标签管理(从基本信息卡触发) ==========
  const tagsLoading = ref(false)
  const tagsData = ref<any[]>([])
  const tagDialogVisible = ref(false)
  const tagDialogType = ref('add')
  const tagFormRef = ref<FormInstance>()
  const tagFormData = reactive({
    id: '',
    tag_key: '',
    tag_value: ''
  })
  const tagRules = {
    tag_key: [{ required: true, message: '请输入或选择标签键', trigger: 'change' }],
    tag_value: [{ required: true, message: '请输入标签值', trigger: 'change' }]
  }

  // 常用标签键(Phase 4 改字典驱动)
  const commonTagKeys = [
    { label: '环境 (environment)', value: 'environment' },
    { label: '业务系统 (business_system)', value: 'business_system' },
    { label: '位置 (location)', value: 'location' },
    { label: '团队 (team)', value: 'team' },
    { label: '数据分类 (data_classification)', value: 'data_classification' }
  ]

  const tagKeyOptionsMap: Record<string, string[]> = {
    environment: ['production', 'staging', 'development', 'testing'],
    business_system: ['hr-system', 'finance-system', 'crm', 'erp', 'oa-system'],
    location: ['beijing', 'shanghai', 'guangzhou', 'shenzhen'],
    team: ['backend', 'frontend', 'devops', 'security'],
    data_classification: ['public', 'internal', 'confidential', 'secret']
  }

  const tagKeyOptions = computed(() => tagKeyOptionsMap[tagFormData.tag_key] || [])

  const loadTags = async () => {
    if (!assetId.value) return
    tagsLoading.value = true
    try {
      const res = await getAssetTags(assetId.value, { page: 1, pageSize: 100 })
      const r: any = res
      const d = r?.data
      tagsData.value = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : []
    } catch {
      tagsData.value = []
    } finally {
      tagsLoading.value = false
    }
  }

  const showTagDialog = (type: string, row?: any) => {
    tagDialogVisible.value = true
    tagDialogType.value = type
    if (type === 'edit' && row) {
      tagFormData.id = row.id
      tagFormData.tag_key = row.tag_key
      tagFormData.tag_value = row.tag_value
    } else {
      tagFormData.id = ''
      tagFormData.tag_key = ''
      tagFormData.tag_value = ''
    }
    nextTick(() => tagFormRef.value?.clearValidate())
  }

  const handleTagSubmit = async () => {
    if (!tagFormRef.value) return
    await tagFormRef.value.validate(async (valid) => {
      if (valid) {
        try {
          const res = await addAssetTag(assetId.value, {
            tag_key: tagFormData.tag_key,
            tag_value: tagFormData.tag_value
          })
          if ((res as any)?.code === 200 || res) {
            ElMessage.success('添加成功')
            tagDialogVisible.value = false
            loadTags()
          } else {
            ElMessage.error((res as any)?.msg || '操作失败')
          }
        } catch (err) {
          ElMessage.error('操作失败')
        }
      }
    })
  }

  const handleDeleteTag = (row: any) => {
    ElMessageBox.confirm(`确定删除标签 ${row.tag_key}?`, '删除标签', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
      .then(async () => {
        try {
          await deleteAssetTag(row.id)
          ElMessage.success('删除成功')
          loadTags()
        } catch {
          ElMessage.error('删除失败')
        }
      })
      .catch(() => {})
  }

  // ========== 告警 Tab ==========
  const alertsLoading = ref(false)
  const alertsData = ref<any[]>([])

  const loadAlerts = async () => {
    if (!assetId.value || !assetDetail.value.asset_ip) return
    alertsLoading.value = true
    try {
      // 优先使用 wazuh_agent_id 查询，更准确
      const agentId = assetDetail.value.wazuh_agent_id
      const params = {
        hours: 24,
        skip: 0,
        limit: 20
      }

      let res
      if (agentId) {
        // 通过 agent_id 查询
        res = await getAlertsByAgentId(agentId, params)
      } else {
        // 没有 agent_id 时使用 IP 查询（降级方案）
        res = await getAlertsByIp(assetDetail.value.asset_ip, params)
      }

      const r: any = res
      const d = r?.data
      alertsData.value = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : []
    } catch {
      alertsData.value = []
    } finally {
      alertsLoading.value = false
    }
  }

  const getAlertLevelType = (level?: number): 'danger' | 'warning' | 'info' | 'success' => {
    if (!level) return 'info'
    if (level >= 12) return 'danger'
    if (level >= 8) return 'warning'
    if (level >= 4) return 'info'
    return 'success'
  }

  // ========== 数据来源 Tab ==========
  const datasourcesLoading = ref(false)
  const datasourcesData = ref<any[]>([])

  // 来源标签映射
  const sourceLabelMap: Record<string, string> = {
    'wazuh': 'Wazuh',
    'tplink-router': 'TP-Link 路由器',
    'nmap': 'Nmap',
    'manual': '手动录入'
  }

  const getSourceStatusTagType = (status: string): 'success' | 'danger' | 'warning' | 'info' => {
    if (status === 'online' || status === 'active') return 'success'
    if (status === 'offline' || status === 'disconnected') return 'danger'
    if (status === 'never_connected' || status === 'pending') return 'warning'
    return 'info'
  }

  const loadDataSources = async () => {
    if (!assetId.value) return
    datasourcesLoading.value = true
    try {
      const res = await getAssetSources(assetId.value)
      const r: any = res
      const d = r?.data
      datasourcesData.value = Array.isArray(d) ? d : []
    } catch (err) {
      console.error('获取数据来源失败:', err)
      datasourcesData.value = []
    } finally {
      datasourcesLoading.value = false
    }
  }

  // ========== 工具函数 ==========
  const formatTime = (time?: string) => {
    if (!time) return '--'
    return new Date(time).toLocaleString('zh-CN')
  }

  const goBack = () => {
    router.push('/assets/list')
  }

  // 加载数据
  onMounted(() => {
    loadDetail()
    loadSummary()
    loadPorts()
    loadTags()
    loadAlerts()
    loadDataSources()
  })
</script>

<style lang="scss" scoped>
  .asset-detail-page {
    padding: 0;
    // 兜底滚动: 在小屏/小笔记本上 (顶部信息卡+摘要卡+Tab 累加高度 > 视口高度)
    // .art-full-height 的 height: var(--art-full-height) 会让内容溢出但不可滚。
    // 这里强制允许页面级滚动, 避免下半截被截断。
    // 大屏 (信息卡+摘要卡 < 视口的 ~70%) 时 Tab 内部 overflow-y 仍生效, 互不冲突。
    overflow: auto;
    // 自适应内容高度 —— 内容超出视口时让父容器随内容伸展
    height: auto;
    min-height: var(--art-full-height);

    .detail-header {
      flex-shrink: 0;
      margin-bottom: 12px;
    }

    .info-card,
    .summary-card {
      flex-shrink: 0;
      margin-bottom: 16px;
    }

    // 取消 tab-card 的 flex:1 + overflow:hidden,
    // 让卡片高度随内容伸展, 避免被父级 scroll 夹住压成 0 高度
    .tab-card {
      flex-shrink: 0;
      margin-bottom: 16px;

      // Tab 内部滚动限制改轻 —— 表格自身有滚动条
      :deep(.el-tabs__content) {
        overflow: visible;
      }

      :deep(.el-tab-pane) {
        height: auto;
        overflow: visible;
      }
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      .title {
        font-size: 16px;
        font-weight: 600;
      }

      .header-tags {
        display: flex;
        gap: 8px;
      }
    }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
    }

    .tab-header {
      margin-bottom: 12px;
      display: flex;
      justify-content: flex-end;
    }

    .text-placeholder {
      color: var(--el-text-color-placeholder, #c0c4cc);
    }

    .high-risk-port {
      color: var(--el-color-danger, #f56c6c);
      font-weight: 600;
    }

    .mr-1 {
      margin-right: 4px;
    }

    .mb-1 {
      margin-bottom: 4px;
    }

    // 数据来源 popover 样式
    .source-meta-popover {
      max-height: 300px;
      overflow-y: auto;

      .source-meta-row {
        display: flex;
        gap: 8px;
        padding: 2px 0;
        font-size: 13px;
        line-height: 1.6;
      }

      .source-meta-key {
        flex-shrink: 0;
        color: var(--el-text-color-secondary, #909399);
        font-weight: 500;
        min-width: 100px;
      }

      .source-meta-value {
        color: var(--el-text-color-primary, #303133);
        word-break: break-all;
      }
    }
  }

  @media (max-width: 1400px) {
    .summary-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    }
  }

  @media (max-width: 900px) {
    .summary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }
  }
</style>
