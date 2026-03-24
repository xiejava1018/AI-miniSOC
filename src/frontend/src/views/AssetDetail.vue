<template>
  <div class="asset-detail">
    <el-page-header @back="goBack" title="返回">
      <template #content>
        <span>资产详情</span>
      </template>
    </el-page-header>

    <el-card style="margin-top: 20px" v-loading="loading">
      <el-descriptions v-if="asset" :column="2" border>
        <el-descriptions-item label="资产名称">{{ asset.name }}</el-descriptions-item>
        <el-descriptions-item label="IP地址">{{ asset.asset_ip }}</el-descriptions-item>
        <el-descriptions-item label="资产类型">{{ asset.asset_type }}</el-descriptions-item>
        <el-descriptions-item label="重要性">{{ asset.criticality }}</el-descriptions-item>
        <el-descriptions-item label="负责人">{{ asset.owner || '-' }}</el-descriptions-item>
        <el-descriptions-item label="业务单元">{{ asset.business_unit || '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ asset.asset_status || '未知' }}</el-descriptions-item>
        <el-descriptions-item label="Wazuh Agent ID">
          {{ asset.wazuh_agent_id || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">
          {{ asset.asset_description || '-' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card style="margin-top: 20px" header="标签" v-loading="tagsLoading">
      <div v-if="tags.length > 0" class="tags-container">
        <el-tag
          v-for="tag in tags"
          :key="tag.id"
          closable
          @close="deleteTag(tag.id)"
          style="margin: 5px"
          type="primary"
        >
          <strong>{{ tag.tag_key }}:</strong> {{ tag.tag_value }}
        </el-tag>
        <el-button
          type="primary"
          link
          style="margin-left: 10px"
          @click="showAddTagDialog = true"
        >
          + 添加标签
        </el-button>
      </div>
      <div v-else>
        <el-empty description="暂无标签" />
        <div style="text-align: center; margin-top: 10px">
          <el-button type="primary" size="small" @click="showAddTagDialog = true">
            添加标签
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card style="margin-top: 20px" header="开放端口" v-loading="portsLoading">
      <div v-if="ports.length > 0">
        <el-table :data="ports" style="width: 100%">
          <el-table-column prop="port" label="端口" width="100" />
          <el-table-column prop="protocol" label="协议" width="100" />
          <el-table-column prop="state" label="状态" width="100">
            <template #default="scope">
              <el-tag
                :type="scope.row.state === 'open' ? 'danger' : 'info'"
                size="small"
              >
                {{ scope.row.state }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="service" label="服务" width="150" />
          <el-table-column prop="version" label="版本" />
          <el-table-column prop="vulnerability" label="漏洞" />
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="scope">
              <el-button link type="primary" size="small" @click="editPort(scope.row)">
                编辑
              </el-button>
              <el-popconfirm
                title="确定删除这个端口吗？"
                @confirm="deletePort(scope.row.id)"
              >
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-else description="暂无端口信息" />
      <div style="margin-top: 10px; text-align: right">
        <el-button type="primary" size="small" @click="showAddPortDialog = true">
          添加端口
        </el-button>
      </div>
    </el-card>

    <el-card style="margin-top: 20px" header="相关事件" v-loading="incidentsLoading">
      <div v-if="incidents.length > 0">
        <el-table :data="incidents" style="width: 100%">
          <el-table-column prop="title" label="事件标题" width="200" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="getStatusType(scope.row.status)" size="small">
                {{ getStatusLabel(scope.row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="severity" label="严重程度" width="100">
            <template #default="scope">
              <el-tag :type="getSeverityType(scope.row.severity)" size="small">
                {{ getSeverityLabel(scope.row.severity) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="assigned_to" label="负责人" width="120" />
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="scope">
              {{ formatDate(scope.row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="scope">
              <el-button link type="primary" size="small" @click="viewIncident(scope.row)">
                查看
              </el-button>
              <el-popconfirm
                title="确定取消关联这个事件吗？"
                @confirm="unlinkIncident(scope.row.id)"
              >
                <template #reference>
                  <el-button link type="danger" size="small">取消关联</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-else description="暂无相关事件" />
      <div style="margin-top: 10px; text-align: right">
        <el-button type="primary" size="small" @click="showLinkIncidentDialog = true">
          关联事件
        </el-button>
      </div>
    </el-card>

    <el-card style="margin-top: 20px" header="相关告警">
      <el-empty description="暂无相关告警" />
    </el-card>

    <!-- 添加标签对话框 -->
    <el-dialog v-model="showAddTagDialog" title="添加标签" width="500px">
      <el-form :model="newTag" label-width="100px">
        <el-form-item label="标签键">
          <el-select
            v-model="newTag.tag_key"
            style="width: 100%"
            placeholder="选择或输入标签键"
            filterable
            allow-create
          >
            <el-option label="环境 (environment)" value="environment" />
            <el-option label="业务系统 (business_system)" value="business_system" />
            <el-option label="位置 (location)" value="location" />
            <el-option label="团队 (team)" value="team" />
            <el-option label="数据分类 (data_classification)" value="data_classification" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签值">
          <el-select
            v-model="newTag.tag_value"
            style="width: 100%"
            placeholder="选择或输入标签值"
            filterable
            allow-create
          >
            <el-option
              v-for="value in getSuggestedValues(newTag.tag_key)"
              :key="value"
              :label="value"
              :value="value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddTagDialog = false">取消</el-button>
        <el-button type="primary" @click="addTag" :loading="tagsLoading">确定</el-button>
      </template>
    </el-dialog>

    <!-- 添加端口对话框 -->
    <el-dialog v-model="showAddPortDialog" title="添加端口" width="500px">
      <el-form :model="newPort" label-width="100px">
        <el-form-item label="端口号">
          <el-input-number v-model="newPort.port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="协议">
          <el-select v-model="newPort.protocol" style="width: 100%">
            <el-option label="TCP" value="tcp" />
            <el-option label="UDP" value="udp" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="newPort.state" style="width: 100%">
            <el-option label="开放" value="open" />
            <el-option label="关闭" value="closed" />
            <el-option label="过滤" value="filtered" />
          </el-select>
        </el-form-item>
        <el-form-item label="服务">
          <el-input v-model="newPort.service" placeholder="如: ssh, http, mysql" />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="newPort.version" placeholder="服务版本信息" />
        </el-form-item>
        <el-form-item label="漏洞">
          <el-input v-model="newPort.vulnerability" type="textarea" placeholder="已知漏洞信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddPortDialog = false">取消</el-button>
        <el-button type="primary" @click="addPort" :loading="portsLoading">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAssetStore } from '@/stores/assets'
import { assetPortsApi, assetTagsApi, assetIncidentsApi } from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const assetStore = useAssetStore()

const loading = ref(false)
const portsLoading = ref(false)
const tagsLoading = ref(false)
const incidentsLoading = ref(false)
const asset = ref<any>(null)
const ports = ref<any[]>([])
const tags = ref<any[]>([])
const incidents = ref<any[]>([])
const showAddPortDialog = ref(false)
const showAddTagDialog = ref(false)
const showLinkIncidentDialog = ref(false)

const newPort = ref({
  port: 80,
  protocol: 'tcp',
  state: 'open',
  service: '',
  version: '',
  vulnerability: ''
})

const newTag = ref({
  tag_key: '',
  tag_value: ''
})

// 常用标签建议值
const tagSuggestions: Record<string, string[]> = {
  environment: ['production', 'staging', 'development', 'testing'],
  business_system: ['hr-system', 'finance-system', 'crm', 'erp', 'oa-system'],
  location: ['beijing', 'shanghai', 'guangzhou', 'shenzhen'],
  team: ['backend', 'frontend', 'devops', 'security'],
  data_classification: ['public', 'internal', 'confidential', 'secret']
}

onMounted(async () => {
  await loadAsset()
  await loadPorts()
  await loadTags()
  await loadIncidents()
})

async function loadAsset() {
  loading.value = true
  try {
    const id = route.params.id as string
    asset.value = await assetStore.fetchAsset(id)
  } catch (error) {
    console.error('获取资产详情失败:', error)
  } finally {
    loading.value = false
  }
}

async function loadPorts() {
  portsLoading.value = true
  try {
    const id = route.params.id as string
    const data = await assetPortsApi.list(id)
    ports.value = data.items || []
  } catch (error) {
    console.error('获取端口列表失败:', error)
  } finally {
    portsLoading.value = false
  }
}

async function loadTags() {
  tagsLoading.value = true
  try {
    const id = route.params.id as string
    const data = await assetTagsApi.list(id)
    tags.value = data.items || []
  } catch (error) {
    console.error('获取标签列表失败:', error)
  } finally {
    tagsLoading.value = false
  }
}

async function addPort() {
  portsLoading.value = true
  try {
    const id = route.params.id as string
    await assetPortsApi.create(id, {
      ...newPort.value,
      asset_ip: asset.value.asset_ip
    })
    ElMessage.success('端口添加成功')
    showAddPortDialog.value = false
    newPort.value = {
      port: 80,
      protocol: 'tcp',
      state: 'open',
      service: '',
      version: '',
      vulnerability: ''
    }
    await loadPorts()
  } catch (error: any) {
    ElMessage.error(error.message || '添加端口失败')
  } finally {
    portsLoading.value = false
  }
}

function editPort(port: any) {
  ElMessage.info('编辑功能待实现')
}

async function deletePort(portId: string) {
  portsLoading.value = true
  try {
    await assetPortsApi.delete(portId)
    ElMessage.success('端口删除成功')
    await loadPorts()
  } catch (error: any) {
    ElMessage.error(error.message || '删除端口失败')
  } finally {
    portsLoading.value = false
  }
}

async function addTag() {
  tagsLoading.value = true
  try {
    const id = route.params.id as string
    await assetTagsApi.create(id, newTag.value)
    ElMessage.success('标签添加成功')
    showAddTagDialog.value = false
    newTag.value = {
      tag_key: '',
      tag_value: ''
    }
    await loadTags()
  } catch (error: any) {
    ElMessage.error(error.message || '添加标签失败')
  } finally {
    tagsLoading.value = false
  }
}

async function deleteTag(tagId: string) {
  tagsLoading.value = true
  try {
    await assetTagsApi.delete(tagId)
    ElMessage.success('标签删除成功')
    await loadTags()
  } catch (error: any) {
    ElMessage.error(error.message || '删除标签失败')
  } finally {
    tagsLoading.value = false
  }
}

async function loadIncidents() {
  incidentsLoading.value = true
  try {
    const id = route.params.id as string
    incidents.value = await assetIncidentsApi.list(id)
  } catch (error) {
    console.error('获取事件列表失败:', error)
  } finally {
    incidentsLoading.value = false
  }
}

async function unlinkIncident(incidentId: string) {
  incidentsLoading.value = true
  try {
    const id = route.params.id as string
    await assetIncidentsApi.unlink(id, incidentId)
    ElMessage.success('取消关联成功')
    await loadIncidents()
  } catch (error: any) {
    ElMessage.error(error.message || '取消关联失败')
  } finally {
    incidentsLoading.value = false
  }
}

function viewIncident(incident: any) {
  router.push(`/incidents/${incident.id}`)
}

function getStatusType(status: string) {
  const types: Record<string, string> = {
    open: '',
    in_progress: 'warning',
    resolved: 'success',
    closed: 'info'
  }
  return types[status] || ''
}

function getStatusLabel(status: string) {
  const labels: Record<string, string> = {
    open: '待处理',
    in_progress: '处理中',
    resolved: '已解决',
    closed: '已关闭'
  }
  return labels[status] || status
}

function getSeverityType(severity: string) {
  const types: Record<string, string> = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    low: ''
  }
  return types[severity] || ''
}

function getSeverityLabel(severity: string) {
  const labels: Record<string, string> = {
    critical: '严重',
    high: '高',
    medium: '中',
    low: '低'
  }
  return labels[severity] || severity
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

function getSuggestedValues(tagKey: string): string[] {
  return tagSuggestions[tagKey] || []
}

function goBack() {
  router.back()
}
</script>

<style scoped>
.asset-detail {
  padding: 20px;
}

.tags-container {
  min-height: 40px;
}
</style>
