<template>
  <div class="assets-page">
    <!-- Page Header -->
    <div class="page-header">
      <div class="header-actions">
        <button class="action-btn secondary" @click="handleManualSync" :disabled="syncLoading">
          <svg v-if="!syncLoading" viewBox="0 0 24 24" fill="none">
            <path
              d="M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z"
              stroke="currentColor"
              stroke-width="2"
            />
            <path d="M12 8V12L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <div v-else class="sync-spinner"></div>
          <span>{{ syncLoading ? '同步中...' : '从Wazuh同步' }}</span>
        </button>

        <button class="action-btn secondary" @click="viewSyncHistory">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M12 8V4L8 8H12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 8V16L8 12H12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M4 12C4 16.4183 7.58172 20 12 20C16.4183 20 20 16.4183 20 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <span>同步历史</span>
        </button>

        <button class="action-btn primary" @click="showCreateDialog = true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M12 5V19M5 12H19" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <span>添加资产</span>
        </button>
      </div>
    </div>

    <!-- Last Sync Alert -->
    <el-alert v-if="lastSyncTime" type="info" :closable="false" style="margin-bottom: 16px">
      最后同步时间: {{ formatDate(lastSyncTime) }}
    </el-alert>

    <!-- Toolbar -->
    <div class="toolbar">
      <!-- 视图切换 -->
      <div class="view-toggle">
        <button
          class="view-btn"
          :class="{ active: viewMode === 'card' }"
          @click="viewMode = 'card'"
          title="卡片视图"
        >
          <svg viewBox="0 0 24 24" fill="none">
            <rect x="3" y="3" width="7" height="7" rx="1" stroke="currentColor" stroke-width="2"/>
            <rect x="14" y="3" width="7" height="7" rx="1" stroke="currentColor" stroke-width="2"/>
            <rect x="3" y="14" width="7" height="7" rx="1" stroke="currentColor" stroke-width="2"/>
            <rect x="14" y="14" width="7" height="7" rx="1" stroke="currentColor" stroke-width="2"/>
          </svg>
        </button>
        <button
          class="view-btn"
          :class="{ active: viewMode === 'list' }"
          @click="viewMode = 'list'"
          title="列表视图"
        >
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 6H20M4 12H20M4 18H20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <!-- 筛选条件 -->
      <div class="filter-group">
        <select v-model="filterType" class="filter-select" @change="handleSearch">
          <option value="">全部类型</option>
          <option value="server">服务器</option>
          <option value="workstation">工作站</option>
          <option value="router">路由器</option>
          <option value="switch">交换机</option>
          <option value="other">其他</option>
        </select>

        <select v-model="filterCriticality" class="filter-select" @change="handleSearch">
          <option value="">全部重要性</option>
          <option value="critical">关键</option>
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
        </select>

        <select v-model="filterStatus" class="filter-select" @change="handleSearch">
          <option value="">全部状态</option>
          <option value="在线">在线</option>
          <option value="离线">离线</option>
          <option value="新发现">新发现</option>
        </select>
      </div>

      <!-- 搜索框和搜索按钮 -->
      <div class="search-group">
        <div class="search-box">
          <svg viewBox="0 0 24 24" fill="none">
            <circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2"/>
            <path d="M21 21L16.65 16.65" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索资产名称、IP地址..."
            class="search-input"
            @keyup.enter="handleSearch"
          />
        </div>
        <button class="search-btn" @click="handleSearch">
          搜索
        </button>
      </div>
    </div>

    <!-- Assets Table -->
    <div class="table-container">
      <div v-if="loading" class="table-loading">
        <div class="loading-spinner"></div>
        <p>加载资产数据...</p>
      </div>

      <div v-else-if="filteredAssets.length === 0" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none">
          <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
          <path d="M3 9H21M9 21V9" stroke="currentColor" stroke-width="2"/>
        </svg>
        <h3>暂无资产</h3>
        <p>点击"添加资产"按钮创建第一个资产</p>
      </div>

      <!-- 卡片视图 -->
      <div v-else-if="viewMode === 'card'" class="assets-grid">
        <div
          v-for="(asset, index) in loadedAssets"
          :key="asset.id"
          class="asset-card"
          :style="{ animationDelay: `${index * 50}ms` }"
        >
          <div class="asset-card-bg">
            <div class="asset-glow"></div>
          </div>

          <div class="asset-header">
            <div class="asset-icon">
              <svg viewBox="0 0 24 24" fill="none">
                <rect x="2" y="2" width="20" height="20" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M6 6H18M6 10H14M6 14H12M6 18H10" stroke="currentColor" stroke-width="2"/>
              </svg>
            </div>
            <div class="asset-status" :class="asset.status || 'online'">
              <div class="status-dot"></div>
            </div>
          </div>

          <div class="asset-body">
            <h3 class="asset-name">{{ asset.name }}</h3>
            <div class="asset-ip">{{ asset.asset_ip }}</div>

            <div class="asset-meta">
              <span class="asset-tag" :class="`type-${asset.asset_type}`">
                {{ getTypeLabel(asset.asset_type) }}
              </span>
              <span class="asset-tag" :class="`criticality-${asset.criticality}`">
                {{ getCriticalityLabel(asset.criticality) }}
              </span>
            </div>

            <div class="asset-footer">
              <div class="asset-owner">
                <svg viewBox="0 0 24 24" fill="none">
                  <path
                    d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2"/>
                </svg>
                <span>{{ asset.owner || '未指定' }}</span>
              </div>

              <div class="asset-actions">
                <button class="action-icon" @click="viewAsset(asset)" title="查看">
                  <svg viewBox="0 0 24 24" fill="none">
                    <path
                      d="M15 12C15 13.6569 13.6569 15 12 15C10.3431 15 9 13.6569 9 12C9 10.3431 10.3431 9 12 9C13.6569 9 15 10.3431 15 12Z"
                      stroke="currentColor"
                      stroke-width="2"
                    />
                    <path
                      d="M3 12C5.4 7.6 8.4 5.4 12 5.4C15.6 5.4 18.6 7.6 21 12C18.6 16.4 15.6 18.6 12 18.6C8.4 18.6 5.4 16.4 3 12Z"
                      stroke="currentColor"
                      stroke-width="2"
                    />
                  </svg>
                </button>
                <button class="action-icon" @click="editAsset(asset)" title="编辑">
                  <svg viewBox="0 0 24 24" fill="none">
                    <path
                      d="M11 4H4C3.46957 4 2.96086 4.21071 2.58579 4.58579C2.21071 4.96086 2 5.46957 2 6V20C2 20.5304 2.21071 21.0391 2.58579 21.4142C2.96086 21.7893 3.46957 22 4 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V13"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M18.5 2.50001C18.8978 2.10219 19.4374 1.87869 20 1.87869C20.5626 1.87869 21.1022 2.10219 21.5 2.50001C21.8978 2.89784 22.1213 3.4374 22.1213 4.00001C22.1213 4.56262 21.8978 5.10219 21.5 5.50001L12 15L8 16L9 12L18.5 2.50001Z"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
                <button class="action-icon danger" @click="deleteAsset(asset)" title="删除">
                  <svg viewBox="0 0 24 24" fill="none">
                    <path
                      d="M3 6H5H21M8 6V4C8 3.46957 8.21071 2.96086 8.58579 2.58579C8.96086 2.21071 9.46957 2 10 2H14C14.5304 2 15.0391 2.21071 15.4142 2.58579C15.7893 2.96086 16 3.46957 16 4V6M19 6V20C19 20.5304 18.7893 21.0391 18.4142 21.4142C18.0391 21.7893 17.5304 22 17 22H7C6.46957 22 5.96086 21.7893 5.58579 21.4142C5.21071 21.0391 5 20.5304 5 20V6H19Z"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 无限滚动 sentinel -->
        <div ref="sentinelRef" class="scroll-sentinel"></div>
      </div>

      <!-- 列表视图 -->
      <div v-else class="assets-list">
        <table class="list-table">
          <thead>
            <tr>
              <th>状态</th>
              <th>资产名称</th>
              <th>IP地址</th>
              <th>类型</th>
              <th>重要性</th>
              <th>负责人</th>
              <th>描述</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="asset in paginatedAssets" :key="asset.id">
              <td>
                <span class="status-badge" :class="getStatusClass(asset.asset_status)">
                  {{ asset.asset_status || '在线' }}
                </span>
              </td>
              <td class="name-cell">{{ asset.name || '-' }}</td>
              <td class="ip-cell">{{ asset.asset_ip }}</td>
              <td>
                <span class="type-badge" :class="`type-${asset.asset_type}`">
                  {{ getTypeLabel(asset.asset_type) }}
                </span>
              </td>
              <td>
                <span class="criticality-badge" :class="`criticality-${asset.criticality}`">
                  {{ getCriticalityLabel(asset.criticality) }}
                </span>
              </td>
              <td>{{ asset.owner || '-' }}</td>
              <td class="desc-cell">{{ asset.asset_description || '-' }}</td>
              <td>
                <div class="table-actions">
                  <button class="action-icon" @click="viewAsset(asset)" title="查看">
                    <svg viewBox="0 0 24 24" fill="none">
                      <path d="M15 12C15 13.6569 13.6569 15 12 15C10.3431 15 9 13.6569 9 12C9 10.3431 10.3431 9 12 9C13.6569 9 15 10.3431 15 12Z" stroke="currentColor" stroke-width="2"/>
                      <path d="M3 12C5.4 7.6 8.4 5.4 12 5.4C15.6 5.4 18.6 7.6 21 12C18.6 16.4 15.6 18.6 12 18.6C8.4 18.6 5.4 16.4 3 12Z" stroke="currentColor" stroke-width="2"/>
                    </svg>
                  </button>
                  <button class="action-icon" @click="editAsset(asset)" title="编辑">
                    <svg viewBox="0 0 24 24" fill="none">
                      <path d="M11 4H4C3.46957 4 2.96086 4.21071 2.58579 4.58579C2.21071 4.96086 2 5.46957 2 6V20C2 20.5304 2.21071 21.0391 2.58579 21.4142C2.96086 21.7893 3.46957 22 4 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                      <path d="M18.5 2.50001C18.8978 2.10219 19.4374 1.87869 20 1.87869C20.5626 1.87869 21.1022 2.10219 21.5 2.50001C21.8978 2.89784 22.1213 3.4374 22.1213 4.00001C22.1213 4.56262 21.8978 5.10219 21.5 5.50001L12 15L8 16L9 12L18.5 2.50001Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                  <button class="action-icon danger" @click="deleteAsset(asset)" title="删除">
                    <svg viewBox="0 0 24 24" fill="none">
                      <path d="M3 6H5H21M8 6V4C8 3.46957 8.21071 2.96086 8.58579 2.58579C8.96086 2.21071 9.46957 2 10 2H14C14.5304 2 15.0391 2.21071 15.4142 2.58579C15.7893 2.96086 16 3.46957 16 4V6M19 6V20C19 20.5304 18.7893 21.0391 18.4142 21.4142C18.0391 21.7893 17.5304 22 17 22H7C6.46957 22 5.96086 21.7893 5.58579 21.4142C5.21071 21.0391 5 20.5304 5 20V6H19Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- 列表分页 -->
        <div class="pagination">
          <div class="pagination-info">
            共 {{ filteredAssets.length }} 条，第 {{ currentPage }}/{{ totalPages }} 页
          </div>
          <div class="pagination-controls">
            <button class="page-btn" :disabled="currentPage === 1" @click="currentPage = 1">首页</button>
            <button class="page-btn" :disabled="currentPage === 1" @click="currentPage--">上一页</button>
            <button class="page-btn" :disabled="currentPage === totalPages" @click="currentPage++">下一页</button>
            <button class="page-btn" :disabled="currentPage === totalPages" @click="currentPage = totalPages">末页</button>
          </div>
          <div class="pagination-size">
            <select v-model="pageSize" @change="currentPage = 1">
              <option :value="10">10条/页</option>
              <option :value="20">20条/页</option>
              <option :value="50">50条/页</option>
              <option :value="100">100条/页</option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="closeDialog">
      <div class="dialog">
        <div class="dialog-header">
          <h2>{{ isEditMode ? '编辑资产' : '添加资产' }}</h2>
          <button class="dialog-close" @click="closeDialog">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>

        <div class="dialog-body">
          <div class="form-group">
            <label>资产名称 <span class="required">*</span></label>
            <input
              v-model="assetForm.name"
              type="text"
              class="form-input"
              placeholder="输入资产名称"
              :class="{ error: formErrors.name }"
            />
            <span v-if="formErrors.name" class="error-text">{{ formErrors.name }}</span>
          </div>

          <div class="form-group">
            <label>IP地址 <span class="required">*</span></label>
            <input
              v-model="assetForm.asset_ip"
              type="text"
              class="form-input"
              placeholder="例如: 192.168.0.100"
              :class="{ error: formErrors.asset_ip }"
            />
            <span v-if="formErrors.asset_ip" class="error-text">{{ formErrors.asset_ip }}</span>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>网络区域</label>
              <select v-model="assetForm.network_segment" class="form-input">
                <option value="default">默认区域</option>
                <option value="internal">内网</option>
                <option value="dmz">DMZ</option>
                <option value="external">外网</option>
                <option value="guest">访客网络</option>
              </select>
            </div>

            <div class="form-group">
              <label>资产状态</label>
              <select v-model="assetForm.asset_status" class="form-input">
                <option value="active">在线</option>
                <option value="inactive">离线</option>
                <option value="retired">报废</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>资产类型</label>
              <select v-model="assetForm.asset_type" class="form-input">
                <option value="server">服务器</option>
                <option value="workstation">工作站</option>
                <option value="router">路由器</option>
                <option value="switch">交换机</option>
                <option value="printer">打印机</option>
                <option value="other">其他</option>
              </select>
            </div>

            <div class="form-group">
              <label>重要性</label>
              <select v-model="assetForm.criticality" class="form-input">
                <option value="critical">关键</option>
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>负责人</label>
              <input
                v-model="assetForm.owner"
                type="text"
                class="form-input"
                placeholder="输入负责人姓名"
              />
            </div>

            <div class="form-group">
              <label>业务单元</label>
              <input
                v-model="assetForm.business_unit"
                type="text"
                class="form-input"
                placeholder="输入业务单元"
              />
            </div>
          </div>

          <div class="form-group">
            <label>MAC地址</label>
            <input
              v-model="assetForm.mac_address"
              type="text"
              class="form-input"
              placeholder="例如: 00:1A:2B:3C:4D:5E"
              :class="{ error: formErrors.mac_address }"
            />
            <span v-if="formErrors.mac_address" class="error-text">{{ formErrors.mac_address }}</span>
          </div>

          <div class="form-group">
            <label>Wazuh Agent ID</label>
            <input
              v-model="assetForm.wazuh_agent_id"
              type="text"
              class="form-input"
              placeholder="输入Wazuh Agent ID"
            />
          </div>

          <div class="form-group">
            <label>描述</label>
            <textarea
              v-model="assetForm.asset_description"
              class="form-textarea"
              placeholder="输入资产描述信息"
              rows="3"
            ></textarea>
          </div>
        </div>

        <div class="dialog-footer">
          <button class="action-btn secondary" @click="closeDialog">取消</button>
          <button class="action-btn primary" @click="isEditMode ? handleUpdate() : handleCreate()">
            {{ isEditMode ? '保存' : '确定' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAssetStore } from '@/stores/assets'
import { syncApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const assetStore = useAssetStore()

const loading = ref(false)
const syncLoading = ref(false)
const assets = ref<any[]>([])
const showCreateDialog = ref(false)
const isEditMode = ref(false)
const editingAssetId = ref<string | null>(null)
const searchQuery = ref('')
const filterType = ref('')
const filterCriticality = ref('')
const filterStatus = ref('')
const viewMode = ref<'card' | 'list'>('card')
const lastSyncTime = ref<string | null>(null)

// 分页相关
const currentPage = ref(1)
const pageSize = ref(10)

// 卡片视图按需加载（无限滚动）
const cardDisplayCount = ref(12)
const loadedAssets = computed(() => {
  return filteredAssets.value.slice(0, cardDisplayCount.value)
})

const hasMoreCards = computed(() => {
  return cardDisplayCount.value < filteredAssets.value.length
})

function loadMoreCards() {
  cardDisplayCount.value += 12
}

// 无限滚动 - 使用 Intersection Observer
let observer: IntersectionObserver | null = null
const sentinelRef = ref<HTMLElement | null>(null)

function setupIntersectionObserver() {
  if (observer) {
    observer.disconnect()
  }

  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && hasMoreCards.value && viewMode.value === 'card') {
        loadMoreCards()
      }
    },
    {
      rootMargin: '100px'
    }
  )

  // 等待 DOM 更新后观察 sentinel 元素
  nextTick(() => {
    if (sentinelRef.value) {
      observer?.observe(sentinelRef.value)
    }
  })
}

onMounted(async () => {
  await loadAssets()
  setupIntersectionObserver()
})

// 清理 observer
onUnmounted(() => {
  if (observer) {
    observer.disconnect()
  }
})

const assetForm = ref({
  name: '',
  network_segment: 'default',
  asset_ip: '',
  asset_type: 'server',
  criticality: 'medium',
  owner: '',
  business_unit: '',
  asset_description: '',
  mac_address: '',
  wazuh_agent_id: '',
  asset_status: 'active'
})

const formErrors = ref<Record<string, string>>({})

// 列表视图分页
const paginatedAssets = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredAssets.value.slice(start, end)
})

const totalPages = computed(() => {
  return Math.ceil(filteredAssets.value.length / pageSize.value) || 1
})

const filteredAssets = computed(() => {
  return assets.value.filter(asset => {
    const searchLower = searchQuery.value.toLowerCase()
    const matchesSearch =
      !searchQuery.value ||
      (asset.name && asset.name.toLowerCase().includes(searchLower)) ||
      asset.asset_ip.includes(searchQuery.value) ||
      (asset.asset_description && asset.asset_description.toLowerCase().includes(searchLower))

    const matchesType = !filterType.value || asset.asset_type === filterType.value
    const matchesCriticality =
      !filterCriticality.value || asset.criticality === filterCriticality.value
    const matchesStatus =
      !filterStatus.value || asset.asset_status === filterStatus.value

    return matchesSearch && matchesType && matchesCriticality && matchesStatus
  })
})

function handleSearch() {
  // 搜索时重置分页
  currentPage.value = 1
  cardDisplayCount.value = 12
  // 搜索功能 - 由于是前端筛选，这里只需要触发重新计算
  // 如果后续需要后端搜索，可以在这里调用 API
  console.log('搜索条件:', {
    searchQuery: searchQuery.value,
    filterType: filterType.value,
    filterCriticality: filterCriticality.value,
    filterStatus: filterStatus.value
  })
}

// 无限滚动处理
function handleScroll() {
  // 只在卡片视图时启用无限滚动
  if (viewMode.value !== 'card') return

  const scrollTop = window.scrollY || document.documentElement.scrollTop
  const scrollHeight = document.documentElement.scrollHeight
  const clientHeight = document.documentElement.clientHeight

  // 当滚动到距离底部100px时加载更多
  if (scrollTop + clientHeight >= scrollHeight - 100) {
    if (hasMoreCards.value) {
      loadMoreCards()
    }
  }
}

onMounted(async () => {
  await loadAssets()
  // 添加滚动监听（卡片视图无限滚动）
  window.addEventListener('scroll', handleScroll)
})

// 移除滚动监听
onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
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

function getTypeLabel(type: string) {
  const labels: Record<string, string> = {
    server: '服务器',
    workstation: '工作站',
    router: '路由器',
    switch: '交换机',
    other: '其他'
  }
  return labels[type] || type
}

function getCriticalityLabel(criticality: string) {
  const labels: Record<string, string> = {
    critical: '关键',
    high: '高',
    medium: '中',
    low: '低'
  }
  return labels[criticality] || criticality
}

function getStatusClass(status: string) {
  if (status === '在线' || status === 'online') return 'online'
  if (status === '离线' || status === 'offline') return 'offline'
  if (status === '新发现' || status === 'new') return 'new'
  return 'online'
}

function viewAsset(asset: any) {
  router.push(`/assets/${asset.id}`)
}

function editAsset(asset: any) {
  isEditMode.value = true
  editingAssetId.value = asset.id
  assetForm.value = {
    name: asset.name || '',
    network_segment: asset.network_segment || 'default',
    asset_ip: asset.asset_ip || '',
    asset_type: asset.asset_type || 'server',
    criticality: asset.criticality || 'medium',
    owner: asset.owner || '',
    business_unit: asset.business_unit || '',
    asset_description: asset.asset_description || '',
    mac_address: asset.mac_address || '',
    wazuh_agent_id: asset.wazuh_agent_id || '',
    asset_status: asset.asset_status || 'active'
  }
  showCreateDialog.value = true
}

async function deleteAsset(asset: any) {
  try {
    await ElMessageBox.confirm(
      `确定要删除资产 "${asset.name}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await assetStore.deleteAsset(asset.id)
    ElMessage.success('资产删除成功')
    await loadAssets()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('删除资产失败:', error)
      ElMessage.error(error.message || '删除资产失败')
    }
  }
}

function closeDialog() {
  showCreateDialog.value = false
  isEditMode.value = false
  editingAssetId.value = null
  assetForm.value = {
    name: '',
    network_segment: 'default',
    asset_ip: '',
    asset_type: 'server',
    criticality: 'medium',
    owner: '',
    business_unit: '',
    asset_description: '',
    mac_address: '',
    wazuh_agent_id: '',
    asset_status: 'active'
  }
  formErrors.value = {}
}

// 表单验证
function validateForm(): boolean {
  formErrors.value = {}

  // 验证资产名称
  if (!assetForm.value.name || assetForm.value.name.trim() === '') {
    formErrors.value.name = '请输入资产名称'
  }

  // 验证IP地址
  if (!assetForm.value.asset_ip || assetForm.value.asset_ip.trim() === '') {
    formErrors.value.asset_ip = '请输入IP地址'
  } else if (!isValidIP(assetForm.value.asset_ip)) {
    formErrors.value.asset_ip = '请输入有效的IP地址'
  }

  // 验证MAC地址（如果填写了）
  if (assetForm.value.mac_address && !isValidMAC(assetForm.value.mac_address)) {
    formErrors.value.mac_address = '请输入有效的MAC地址格式（如：00:1A:2B:3C:4D:5E）'
  }

  return Object.keys(formErrors.value).length === 0
}

// IP地址验证
function isValidIP(ip: string): boolean {
  const ipPattern = /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/
  return ipPattern.test(ip)
}

// MAC地址验证
function isValidMAC(mac: string): boolean {
  const macPattern = /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/
  return macPattern.test(mac)
}

async function handleUpdate() {
  if (!editingAssetId.value) return

  // 验证表单
  if (!validateForm()) {
    return
  }

  try {
    await assetStore.updateAsset(editingAssetId.value, assetForm.value)
    ElMessage.success('资产更新成功')
    closeDialog()
    await loadAssets()
  } catch (error: any) {
    console.error('更新资产失败:', error)
    ElMessage.error(error.response?.data?.detail || error.message || '更新资产失败')
  }
}

async function syncAssets() {
  try {
    loading.value = true
    await fetch('http://localhost:8000/api/v1/assets/sync/from-wazuh', { method: 'POST' })
    await loadAssets()
  } catch (error) {
    console.error('同步失败:', error)
  } finally {
    loading.value = false
  }
}

async function handleManualSync() {
  syncLoading.value = true
  try {
    const result = await syncApi.manualSync()
    ElMessage.success('同步任务已创建')
    router.push(`/sync-tasks/${result.task_id}`)
  } catch (error) {
    console.error('创建同步任务失败:', error)
    ElMessage.error('创建同步任务失败')
  } finally {
    syncLoading.value = false
  }
}

function viewSyncHistory() {
  router.push('/sync-tasks')
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString('zh-CN')
}

async function handleCreate() {
  // 验证表单
  if (!validateForm()) {
    return
  }

  try {
    await assetStore.createAsset(assetForm.value)
    ElMessage.success('资产创建成功')
    closeDialog()
    await loadAssets()
  } catch (error: any) {
    console.error('创建资产失败:', error)
    ElMessage.error(error.response?.data?.detail || error.message || '创建资产失败')
  }
}
</script>

<style scoped>
.assets-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  max-width: 100%;
}

/* Page Header */
.page-header {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-bottom: 16px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-base);
  border: none;
}

.action-btn svg {
  width: 18px;
  height: 18px;
}

.action-btn.primary {
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
  color: white;
  box-shadow: 0 4px 12px var(--accent-cyan-dim);
}

.action-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px var(--accent-cyan-dim);
}

.action-btn.secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.action-btn.secondary:hover {
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.05);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.sync-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Toolbar */
.toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.view-toggle {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.view-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.view-btn svg {
  width: 18px;
  height: 18px;
}

.view-btn:hover {
  color: var(--text-primary);
  background: rgba(0, 212, 255, 0.1);
}

.view-btn.active {
  color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.15);
}

.filter-group {
  display: flex;
  gap: 12px;
}

.filter-select {
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.filter-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.search-group {
  display: flex;
  gap: 8px;
  flex: 1;
}

.search-box {
  flex: 1;
  min-width: 200px;
  position: relative;
  display: flex;
  align-items: center;
}

.search-box svg {
  position: absolute;
  left: 14px;
  width: 18px;
  height: 18px;
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 10px 14px 10px 44px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  transition: all var(--transition-fast);
}

.search-btn {
  padding: 10px 24px;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.search-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px var(--accent-cyan-dim);
}

.search-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 3px var(--accent-cyan-dim);
}

.search-input::placeholder {
  color: var(--text-muted);
}

/* View Toggle Bar */
.view-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
}

.view-toggle {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.view-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.view-btn svg {
  width: 18px;
  height: 18px;
}

.view-btn:hover {
  color: var(--text-primary);
  background: rgba(0, 212, 255, 0.1);
}

.view-btn.active {
  color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.15);
}

/* Table Container */
.table-container {
  min-height: 400px;
}

.table-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-muted);
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--bg-tertiary);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-muted);
}

.empty-state svg {
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state h3 {
  font-size: 18px;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.empty-state p {
  font-size: 14px;
  margin: 0;
}

/* Assets Grid */
.assets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

/* 无限滚动 sentinel */
.scroll-sentinel {
  height: 1px;
  grid-column: 1 / -1;
}

/* 分页样式 */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--bg-tertiary);
  border-top: 1px solid var(--border-color);
}

.pagination-info {
  font-size: 13px;
  color: var(--text-secondary);
}

.pagination-controls {
  display: flex;
  gap: 8px;
}

.page-btn {
  padding: 8px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.page-btn:hover:not(:disabled) {
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.1);
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination-size select {
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}

.pagination-size select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

/* Assets List */
.assets-list {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  overflow: hidden;
}

.list-table {
  width: 100%;
  border-collapse: collapse;
}

.list-table th,
.list-table td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.list-table th {
  background: var(--bg-tertiary);
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.list-table tr:hover {
  background: rgba(0, 212, 255, 0.03);
}

.list-table tr:last-child td {
  border-bottom: none;
}

.name-cell {
  font-weight: 500;
  color: var(--text-primary);
}

.ip-cell {
  font-family: 'JetBrains Mono', monospace;
  color: var(--accent-cyan);
}

.desc-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-muted);
}

.table-actions {
  display: flex;
  gap: 8px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.online {
  background: rgba(16, 185, 129, 0.15);
  color: var(--status-success);
}

.status-badge.offline {
  background: rgba(107, 114, 128, 0.15);
  color: var(--text-muted);
}

.status-badge.new {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan);
}

.type-badge,
.criticality-badge {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.type-badge.type-server {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan);
}

.type-badge.type-workstation {
  background: rgba(139, 92, 246, 0.15);
  color: var(--accent-purple);
}

.type-badge.type-router {
  background: rgba(255, 193, 7, 0.15);
  color: var(--status-warning);
}

.type-badge.type-switch {
  background: rgba(16, 185, 129, 0.15);
  color: var(--status-success);
}

.type-badge.type-other {
  background: rgba(107, 114, 128, 0.15);
  color: var(--text-muted);
}

.criticality-badge.criticality-critical {
  background: rgba(255, 42, 109, 0.15);
  color: var(--status-critical);
}

.criticality-badge.criticality-high {
  background: rgba(255, 107, 53, 0.15);
  color: var(--status-high);
}

.criticality-badge.criticality-medium {
  background: rgba(255, 193, 7, 0.15);
  color: var(--status-warning);
}

.criticality-badge.criticality-low {
  background: rgba(107, 114, 128, 0.15);
  color: var(--text-muted);
}

.asset-card {
  position: relative;
  padding: 20px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  overflow: hidden;
  animation: fadeInUp 0.4s ease forwards;
  opacity: 0;
  cursor: pointer;
  transition: all var(--transition-base);
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.asset-card:hover {
  border-color: var(--accent-cyan);
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.asset-card-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.asset-glow {
  position: absolute;
  top: -50%;
  right: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle, var(--accent-cyan-dim) 0%, transparent 70%);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.asset-card:hover .asset-glow {
  opacity: 1;
}

.asset-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  position: relative;
}

.asset-icon {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(0, 212, 255, 0.05));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-cyan);
}

.asset-icon svg {
  width: 22px;
  height: 22px;
}

.asset-status {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.asset-status.online .status-dot {
  width: 8px;
  height: 8px;
  background: var(--status-success);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--status-success);
}

.asset-status.offline .status-dot {
  width: 8px;
  height: 8px;
  background: var(--text-muted);
  border-radius: 50%;
}

.asset-body {
  position: relative;
}

.asset-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.asset-ip {
  font-size: 13px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 12px;
}

.asset-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.asset-tag {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.asset-tag.type-server {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan);
}

.asset-tag.type-workstation {
  background: rgba(139, 92, 246, 0.15);
  color: var(--accent-purple);
}

.asset-tag.type-router {
  background: rgba(255, 193, 7, 0.15);
  color: var(--status-warning);
}

.asset-tag.type-switch {
  background: rgba(16, 185, 129, 0.15);
  color: var(--status-success);
}

.asset-tag.criticality-critical {
  background: rgba(255, 42, 109, 0.15);
  color: var(--status-critical);
}

.asset-tag.criticality-high {
  background: rgba(255, 107, 53, 0.15);
  color: var(--status-high);
}

.asset-tag.criticality-medium {
  background: rgba(255, 193, 7, 0.15);
  color: var(--status-warning);
}

.asset-tag.criticality-low {
  background: rgba(107, 114, 128, 0.15);
  color: var(--text-muted);
}

.asset-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.asset-owner {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.asset-owner svg {
  width: 16px;
  height: 16px;
}

.asset-actions {
  display: flex;
  gap: 8px;
}

.action-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.action-icon:hover {
  color: var(--text-primary);
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.08);
}

.action-icon.danger:hover {
  border-color: var(--status-critical);
  background: rgba(255, 42, 109, 0.08);
  color: var(--status-critical);
}

.action-icon svg {
  width: 16px;
  height: 16px;
}

/* Dialog */
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(10, 14, 23, 0.8);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.dialog {
  width: 100%;
  max-width: 500px;
  background: var(--bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: 16px;
  box-shadow: var(--shadow-lg);
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid var(--border-color);
}

.dialog-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.dialog-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.dialog-close:hover {
  color: var(--text-primary);
  border-color: var(--status-critical);
  background: rgba(255, 42, 109, 0.08);
}

.dialog-close svg {
  width: 16px;
  height: 16px;
}

.dialog-body {
  padding: 24px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  transition: all var(--transition-fast);
}

.form-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 3px var(--accent-cyan-dim);
}

.form-input.error {
  border-color: var(--status-critical);
}

.form-textarea {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  transition: all var(--transition-fast);
  resize: vertical;
  font-family: inherit;
}

.form-textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 3px var(--accent-cyan-dim);
}

.required {
  color: var(--status-critical);
  margin-left: 2px;
}

.error-text {
  display: block;
  font-size: 12px;
  color: var(--status-critical);
  margin-top: 4px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 24px;
  border-top: 1px solid var(--border-color);
}
</style>
