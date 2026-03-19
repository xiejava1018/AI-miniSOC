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
          {{ asset.description || '-' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card style="margin-top: 20px" header="相关事件">
      <el-empty description="暂无相关事件" />
    </el-card>

    <el-card style="margin-top: 20px" header="相关告警">
      <el-empty description="暂无相关告警" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAssetStore } from '@/stores/assets'

const router = useRouter()
const route = useRoute()
const assetStore = useAssetStore()

const loading = ref(false)
const asset = ref<any>(null)

onMounted(async () => {
  await loadAsset()
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

function goBack() {
  router.back()
}
</script>

<style scoped>
.asset-detail {
  padding: 20px;
}
</style>
