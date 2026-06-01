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
        <ElDescriptionsItem label="MAC地址">{{ assetDetail.mac_address || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="负责人">{{ assetDetail.owner || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="业务单元">{{ assetDetail.business_unit || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="操作系统">
          {{ assetDetail.os_name ? `${assetDetail.os_name} ${assetDetail.os_version || ''}`.trim() : '--' }}
        </ElDescriptionsItem>
        <ElDescriptionsItem label="Wazuh Agent">{{ assetDetail.wazuh_agent_id || '--' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="创建时间">{{ formatTime(assetDetail.created_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="更新时间">{{ formatTime(assetDetail.updated_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="状态更新">{{ formatTime(assetDetail.status_updated_at) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="描述" :span="3">{{ assetDetail.asset_description || '--' }}</ElDescriptionsItem>
      </ElDescriptions>
    </ElCard>

    <!-- Tab 区域 -->
    <ElCard shadow="never" class="tab-card" style="margin-top: 16px">
      <ElTabs v-model="activeTab">
        <!-- 端口管理 -->
        <ElTabPane label="端口管理" name="ports">
          <div class="tab-header">
            <ElButton type="primary" size="small" @click="showPortDialog('add')">添加端口</ElButton>
          </div>
          <ElTable :data="portsData" v-loading="portsLoading" border stripe style="width: 100%">
            <ElTableColumn prop="port" label="端口" width="80" align="center" />
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
            <ElTableColumn prop="scan_time" label="扫描时间" width="170" align="center">
              <template #default="{ row }">{{ formatTime(row.scan_time) }}</template>
            </ElTableColumn>
            <ElTableColumn label="操作" width="100" align="center" fixed="right">
              <template #default="{ row }">
                <ElButton type="danger" link size="small" @click="handleDeletePort(row)">删除</ElButton>
              </template>
            </ElTableColumn>
          </ElTable>
        </ElTabPane>

        <!-- 标签管理 -->
        <ElTabPane label="标签管理" name="tags">
          <div class="tab-header">
            <ElButton type="primary" size="small" @click="showTagDialog('add')">添加标签</ElButton>
          </div>
          <ElTable :data="tagsData" v-loading="tagsLoading" border stripe style="width: 100%">
            <ElTableColumn prop="tag_key" label="标签键" width="160" align="center" />
            <ElTableColumn prop="tag_value" label="标签值" min-width="200" align="center" />
            <ElTableColumn prop="created_at" label="创建时间" width="170" align="center">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </ElTableColumn>
            <ElTableColumn label="操作" width="140" align="center" fixed="right">
              <template #default="{ row }">
                <ElButton type="primary" link size="small" @click="showTagDialog('edit', row)">编辑</ElButton>
                <ElButton type="danger" link size="small" @click="handleDeleteTag(row)">删除</ElButton>
              </template>
            </ElTableColumn>
          </ElTable>
        </ElTabPane>

        <!-- 关联事件 -->
        <ElTabPane label="关联事件" name="incidents">
          <ElTable :data="incidentsData" v-loading="incidentsLoading" border stripe style="width: 100%">
            <ElTableColumn prop="title" label="事件标题" min-width="200" align="center" />
            <ElTableColumn prop="severity" label="严重性" width="100" align="center">
              <template #default="{ row }">
                <ElTag :type="getSeverityType(row.severity)" size="small" effect="light">
                  {{ row.severity || '--' }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="status" label="状态" width="100" align="center">
              <template #default="{ row }">
                <ElTag type="info" size="small" effect="light">{{ row.status || '--' }}</ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="created_at" label="创建时间" width="170" align="center">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </ElTableColumn>
          </ElTable>
          <ElEmpty v-if="!incidentsLoading && incidentsData.length === 0" description="暂无关联事件" />
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

    <!-- 标签弹窗 -->
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
            v-if="tagDialogType === 'add'"
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
          <ElInput v-else v-model="tagFormData.tag_key" disabled />
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
  import { ref, reactive, computed, onMounted, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { ArrowLeft } from '@element-plus/icons-vue'
  import { FormInstance } from 'element-plus'
  import { ElMessageBox, ElMessage } from 'element-plus'
  import {
    getAssetDetail,
    getAssetPorts,
    addAssetPort,
    deleteAssetPort,
    getAssetTags,
    addAssetTag,
    updateAssetTag,
    deleteAssetTag,
    getCommonTagKeys,
    getAssetIncidents
  } from '@/api/asset'
  import { useDictStore } from '@/store/modules/dict'

  const route = useRoute()
  const router = useRouter()
  const assetId = computed(() => route.params.id as string)
  const dictStore = useDictStore()

  // 字典映射
  const assetTypeLabelMap = computed(() => dictStore.getLabelMap('asset_type'))
  const criticalityLabelMap = computed(() => dictStore.getLabelMap('severity'))
  const criticalityColorMap = computed(() => dictStore.getColorMap('severity'))
  const statusLabelMap = computed(() => dictStore.getLabelMap('asset_status'))
  const statusColorMap = computed(() => dictStore.getColorMap('asset_status'))
  const dataSourceLabelMap = computed(() => dictStore.getLabelMap('data_source'))
  const severityColorMap = computed(() => dictStore.getColorMap('severity'))

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

  // Tab
  const activeTab = ref('ports')

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

  const showPortDialog = (type: string) => {
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

  // ========== 标签管理 ==========
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

  // 常用标签键
  const commonTagKeys = [
    { label: '环境 (environment)', value: 'environment' },
    { label: '业务系统 (business_system)', value: 'business_system' },
    { label: '位置 (location)', value: 'location' },
    { label: '团队 (team)', value: 'team' },
    { label: '数据分类 (data_classification)', value: 'data_classification' }
  ]

  // 根据标签键提供可选值
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
          let res
          if (tagDialogType.value === 'add') {
            res = await addAssetTag(assetId.value, {
              tag_key: tagFormData.tag_key,
              tag_value: tagFormData.tag_value
            })
          } else {
            res = await updateAssetTag(tagFormData.id, {
              tag_value: tagFormData.tag_value
            })
          }
          if ((res as any)?.code === 200 || res) {
            ElMessage.success(tagDialogType.value === 'add' ? '添加成功' : '更新成功')
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
    ElMessageBox.confirm(`确定删除标签 ${row.tag_key}？`, '删除标签', {
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

  // ========== 关联事件 ==========
  const incidentsLoading = ref(false)
  const incidentsData = ref<any[]>([])

  const loadIncidents = async () => {
    if (!assetId.value) return
    incidentsLoading.value = true
    try {
      const res = await getAssetIncidents(assetId.value)
      const r: any = res
      const d = r?.data
      incidentsData.value = Array.isArray(d) ? d : Array.isArray(d?.items) ? d.items : []
    } catch {
      incidentsData.value = []
    } finally {
      incidentsLoading.value = false
    }
  }

  // ========== 工具函数 ==========
  const formatTime = (time?: string) => {
    if (!time) return '--'
    return new Date(time).toLocaleString('zh-CN')
  }

  const getSeverityType = (severity?: string): any => {
    return severityColorMap.value[severity || ''] || 'info'
  }

  const goBack = () => {
    router.push('/assets/list')
  }

  const nextTick = (fn: () => void) => {
    setTimeout(fn, 0)
  }

  // 加载数据
  onMounted(() => {
    loadDetail()
    loadPorts()
    loadTags()
    loadIncidents()
  })
</script>

<style lang="scss" scoped>
  .asset-detail-page {
    padding: 0;

    .detail-header {
      margin-bottom: 12px;
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

    .tab-header {
      margin-bottom: 12px;
      display: flex;
      justify-content: flex-end;
    }
  }
</style>
