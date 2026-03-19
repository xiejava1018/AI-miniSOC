<template>
  <div class="assets-page">
    <div class="page-header">
      <h2>资产管理</h2>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        添加资产
      </el-button>
    </div>

    <el-card>
      <el-table :data="assets" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="asset_ip" label="IP地址" />
        <el-table-column prop="asset_type" label="类型">
          <template #default="{ row }">
            <el-tag>{{ row.asset_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="criticality" label="重要性">
          <template #default="{ row }">
            <el-tag :type="getCriticalityType(row.criticality)">
              {{ row.criticality }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="owner" label="负责人" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="viewAsset(row)">查看</el-button>
            <el-button size="small" type="primary" @click="editAsset(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteAsset(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑资产对话框 -->
    <el-dialog v-model="showCreateDialog" title="添加资产" width="600px">
      <el-form :model="assetForm" label-width="120px">
        <el-form-item label="资产名称">
          <el-input v-model="assetForm.name" />
        </el-form-item>
        <el-form-item label="IP地址">
          <el-input v-model="assetForm.asset_ip" />
        </el-form-item>
        <el-form-item label="资产类型">
          <el-select v-model="assetForm.asset_type">
            <el-option label="服务器" value="server" />
            <el-option label="工作站" value="workstation" />
            <el-option label="路由器" value="router" />
            <el-option label="交换机" value="switch" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="重要性">
          <el-select v-model="assetForm.criticality">
            <el-option label="关键" value="critical" />
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-input v-model="assetForm.owner" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { useAssetStore } from '@/stores/assets'

const router = useRouter()
const assetStore = useAssetStore()

const loading = ref(false)
const assets = ref<any[]>([])
const showCreateDialog = ref(false)
const assetForm = ref({
  name: '',
  asset_ip: '',
  asset_type: 'server',
  criticality: 'medium',
  owner: ''
})

onMounted(async () => {
  await loadAssets()
})

async function loadAssets() {
  loading.value = true
  try {
    await assetStore.fetchAssets()
    assets.value = assetStore.assets
  } finally {
    loading.value = false
  }
}

function getCriticalityType(criticality: string) {
  const map: Record<string, string> = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    low: 'info'
  }
  return map[criticality] || 'info'
}

function viewAsset(asset: any) {
  router.push(`/assets/${asset.id}`)
}

function editAsset(asset: any) {
  // TODO: 实现编辑功能
  console.log('编辑资产:', asset)
}

async function deleteAsset(asset: any) {
  // TODO: 实现删除功能
  console.log('删除资产:', asset)
}

async function handleCreate() {
  try {
    await assetStore.createAsset(assetForm.value)
    showCreateDialog.value = false
    await loadAssets()
  } catch (error) {
    console.error('创建资产失败:', error)
  }
}
</script>

<style scoped>
.assets-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
</style>
