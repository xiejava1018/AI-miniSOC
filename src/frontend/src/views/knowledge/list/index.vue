<!--
  运维知识库（P3/F2.3）
  - 顶部 AI 搜索（召回 + GLM rerank，结果卡片化 + 反馈闭环）
  - 列表：分类/复审状态过滤，待复审标黄（老化队列）
  - 新建/编辑弹窗、人工验证（confidence 90）、AI 提取（从已解决事件）
-->
<template>
  <div class="knowledge-page art-full-height">
    <!-- AI 搜索区 -->
    <ElCard shadow="never" class="search-card">
      <div class="ai-search-row">
        <ElIcon class="ai-search-icon"><MagicStick /></ElIcon>
        <ElInput
          v-model="searchQuestion"
          placeholder="用自然语言搜运维知识，例如「SSH 爆破怎么处理」「CentOS 升级注意事项」"
          clearable
          @keyup.enter="handleSearch"
        />
        <ElButton type="primary" :loading="searchLoading" @click="handleSearch">搜索</ElButton>
      </div>
      <div v-if="searchResult" class="search-result">
        <div class="search-result-head">
          <span>
            找到 {{ searchResult.results.length }} 条相关知识
            <ElTag v-if="searchResult.rerank_source" size="small" effect="plain" class="ml-2">
              {{ searchResult.rerank_source === 'glm' ? 'GLM 重排' : '关键词召回' }}
            </ElTag>
          </span>
          <AiFeedback target-type="knowledge" :target-id="searchResult.question" />
        </div>
        <ElAlert v-if="searchResult.message" :title="searchResult.message" type="info" :closable="false" class="mt-2" />
        <div v-for="item in searchResult.results" :key="item.id" class="result-card"
             :class="{ 'is-stale': item.review_status === 'pending_review' }">
          <div class="result-card-head">
            <span class="result-title">{{ item.title }}</span>
            <span class="result-meta">
              <ElTag size="small" effect="plain">{{ categoryLabel(item.category) }}</ElTag>
              <ElTag v-if="item.review_status === 'pending_review'" size="small" type="warning">待复审</ElTag>
              <span class="confidence">置信 {{ item.confidence_score }}</span>
            </span>
          </div>
          <pre class="result-content">{{ item.content }}</pre>
        </div>
      </div>
    </ElCard>

    <!-- 列表区 -->
    <ElCard shadow="never" class="table-card">
      <ArtTableHeader :columnList="[]" v-model:columns="columnChecks" @refresh="loadList">
        <template #left>
          <ElSelect v-model="filterCategory" placeholder="全部分类" clearable style="width: 130px" @change="loadList">
            <ElOption v-for="c in CATEGORY_OPTIONS" :key="c.value" :label="c.label" :value="c.value" />
          </ElSelect>
          <ElSelect v-model="filterStatus" placeholder="全部状态" clearable style="width: 120px" @change="loadList">
            <ElOption label="正常" value="active" />
            <ElOption label="待复审" value="pending_review" />
          </ElSelect>
          <ElButton v-if="hasAuth('add')" type="primary" @click="openDialog()">新增知识</ElButton>
          <ElButton v-if="hasAuth('auto_extract')" :loading="extracting" @click="handleAutoExtract">
            AI 提取
          </ElButton>
        </template>
      </ArtTableHeader>

      <ElTable :data="items" v-loading="loading" border stripe>
        <ElTableColumn label="标题" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="table-title" :class="{ 'is-stale-text': row.review_status === 'pending_review' }">
              {{ row.title }}
            </span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="分类" width="100" align="center">
          <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
        </ElTableColumn>
        <ElTableColumn label="标签" min-width="150">
          <template #default="{ row }">
            <ElTag v-for="t in row.tags" :key="t" size="small" effect="light" class="mr-1">{{ t }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="来源" width="110" align="center">
          <template #default="{ row }">{{ sourceLabel(row.source_type) }}</template>
        </ElTableColumn>
        <ElTableColumn label="置信" width="80" align="center">
          <template #default="{ row }">
            <span :class="row.confidence_score >= 90 ? 'text-success' : ''">{{ row.confidence_score }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="90" align="center">
          <template #default="{ row }">
            <ElTag v-if="row.review_status === 'pending_review'" type="warning" size="small">待复审</ElTag>
            <ElTag v-else type="success" size="small" effect="plain">正常</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="更新时间" width="160" align="center">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <ElButton v-if="hasAuth('edit')" link type="primary" size="small" @click="openDialog(row)">编辑</ElButton>
            <ElButton v-if="hasAuth('validate')" link type="success" size="small" @click="handleValidate(row)">
              验证
            </ElButton>
            <ElButton link type="danger" size="small" @click="handleDelete(row)">删除</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>
      <div class="pagination-row">
        <ElPagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadList"
        />
      </div>
    </ElCard>

    <!-- 新建/编辑弹窗 -->
    <ElDialog v-model="dialogVisible" :title="editing ? '编辑知识' : '新增知识'" width="640px">
      <ElForm :model="form" label-width="70px">
        <ElFormItem label="标题" required>
          <ElInput v-model="form.title" maxlength="120" show-word-limit placeholder="简明扼要的知识标题" />
        </ElFormItem>
        <ElFormItem label="分类">
          <ElSelect v-model="form.category" style="width: 200px">
            <ElOption v-for="c in CATEGORY_OPTIONS" :key="c.value" :label="c.label" :value="c.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="标签">
          <ElInput v-model="form.tagsInput" placeholder="逗号分隔，如：SSH,暴力破解,加固" />
        </ElFormItem>
        <ElFormItem label="正文" required>
          <ElInput
            v-model="form.content"
            type="textarea"
            :rows="10"
            placeholder="建议结构：【故障】…\n【原因】…\n【解决方案】…"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="handleSave">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, onMounted } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { MagicStick } from '@element-plus/icons-vue'
  import {
    getKnowledgeList,
    searchKnowledge,
    createKnowledge,
    updateKnowledge,
    deleteKnowledge,
    validateKnowledge,
    autoExtractKnowledge,
    type KnowledgeItem,
    type KnowledgeSearchResult
  } from '@/api/knowledge'
  import AiFeedback from '@/components/business/ai-feedback/index.vue'
  import { useAuth } from '@/hooks/core/useAuth'

  defineOptions({ name: 'KnowledgeList' })

  const { hasAuth } = useAuth()

  const CATEGORY_OPTIONS = [
    { value: 'troubleshooting', label: '故障排查' },
    { value: 'configuration', label: '配置管理' },
    { value: 'policy', label: '安全策略' },
    { value: 'reference', label: '参考资料' }
  ]
  const categoryLabel = (v?: string) => CATEGORY_OPTIONS.find((c) => c.value === v)?.label || v || '-'
  const sourceLabel = (v?: string) =>
    ({ incident_summary: '事件提取', manual: '手动录入', ai_generated: 'AI 生成' })[v || ''] || v || '-'
  const formatTime = (t?: string) => (t ? new Date(t).toLocaleString('zh-CN') : '--')

  // ---------- 搜索 ----------
  const searchQuestion = ref('')
  const searchLoading = ref(false)
  const searchResult = ref<KnowledgeSearchResult | null>(null)

  const handleSearch = async () => {
    const q = searchQuestion.value.trim()
    if (!q) return
    searchLoading.value = true
    try {
      const res = await searchKnowledge(q)
      if (res.code === 200) searchResult.value = res.data
      else ElMessage.error(res.msg || '搜索失败')
    } catch {
      ElMessage.error('搜索请求失败')
    } finally {
      searchLoading.value = false
    }
  }

  // ---------- 列表 ----------
  const items = ref<KnowledgeItem[]>([])
  const loading = ref(false)
  const total = ref(0)
  const page = ref(1)
  const pageSize = 20
  const filterCategory = ref('')
  const filterStatus = ref('')
  const columnChecks = ref([])

  const loadList = async () => {
    loading.value = true
    try {
      const res = await getKnowledgeList({
        category: filterCategory.value || undefined,
        review_status: filterStatus.value || undefined,
        skip: (page.value - 1) * pageSize,
        limit: pageSize
      })
      if (res.code === 200) {
        items.value = res.data.items
        total.value = res.data.total
      }
    } catch {
      ElMessage.error('列表加载失败')
    } finally {
      loading.value = false
    }
  }

  // ---------- 新建/编辑 ----------
  const dialogVisible = ref(false)
  const editing = ref<KnowledgeItem | null>(null)
  const saving = ref(false)
  const form = ref({ title: '', content: '', category: 'troubleshooting', tagsInput: '' })

  const openDialog = (row?: KnowledgeItem) => {
    editing.value = row || null
    form.value = {
      title: row?.title || '',
      content: row?.content || '',
      category: row?.category || 'troubleshooting',
      tagsInput: (row?.tags || []).join(', ')
    }
    dialogVisible.value = true
  }

  const handleSave = async () => {
    if (!form.value.title.trim() || !form.value.content.trim()) {
      ElMessage.warning('标题和正文不能为空')
      return
    }
    saving.value = true
    try {
      const payload = {
        title: form.value.title.trim(),
        content: form.value.content,
        category: form.value.category,
        tags: form.value.tagsInput.split(/[,，]/).map((t) => t.trim()).filter(Boolean)
      }
      const res = editing.value
        ? await updateKnowledge(editing.value.id, payload)
        : await createKnowledge(payload)
      if (res.code === 200) {
        ElMessage.success(editing.value ? '已更新' : '已创建')
        dialogVisible.value = false
        loadList()
      } else {
        ElMessage.error(res.msg || '保存失败')
      }
    } catch {
      ElMessage.error('保存请求失败')
    } finally {
      saving.value = false
    }
  }

  // ---------- 验证 / 删除 / AI 提取 ----------
  const handleValidate = async (row: KnowledgeItem) => {
    const res = await validateKnowledge(row.id)
    if (res.code === 200) {
      ElMessage.success('已验证（置信度提升至 90）')
      loadList()
    }
  }

  const handleDelete = (row: KnowledgeItem) => {
    ElMessageBox.confirm(`确定删除知识「${row.title}」？`, '删除确认', { type: 'warning' })
      .then(async () => {
        const res = await deleteKnowledge(row.id)
        if (res.code === 200) {
          ElMessage.success('已删除')
          loadList()
        } else {
          ElMessage.error(res.msg || '删除失败')
        }
      })
      .catch(() => {})
  }

  const extracting = ref(false)
  const handleAutoExtract = async () => {
    extracting.value = true
    try {
      const res = await autoExtractKnowledge(90)
      if (res.code === 200) {
        const s = res.data.stats
        ElMessage.success(
          `提取完成：候选 ${s.candidates}，生成 ${s.extracted} 条（GLM ${s.source.glm} / 模板 ${s.source.rule}）`
        )
        loadList()
      } else {
        ElMessage.error(res.msg || '提取失败')
      }
    } catch {
      ElMessage.error('提取请求失败（事件量大时耗时较长，可稍后刷新）')
    } finally {
      extracting.value = false
    }
  }

  onMounted(loadList)
</script>

<style lang="scss" scoped>
  .knowledge-page {
    .search-card {
      margin-bottom: 12px;

      .ai-search-row {
        display: flex;
        align-items: center;
        gap: 8px;

        .ai-search-icon {
          color: var(--el-color-primary);
          font-size: 18px;
        }
      }

      .search-result {
        margin-top: 10px;
        padding-top: 10px;
        border-top: 1px dashed var(--el-border-color-lighter);

        .search-result-head {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 13px;
          margin-bottom: 8px;
        }

        .result-card {
          padding: 10px 12px;
          border: 1px solid var(--el-border-color-lighter);
          border-radius: 6px;
          margin-bottom: 8px;

          &.is-stale {
            border-color: var(--el-color-warning-light-5);
            background: var(--el-color-warning-light-9, #fdf6ec);
          }

          .result-card-head {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;

            .result-title {
              font-weight: 600;
              font-size: 13px;
            }

            .result-meta {
              display: inline-flex;
              align-items: center;
              gap: 6px;

              .confidence {
                font-size: 12px;
                color: var(--el-text-color-secondary);
              }
            }
          }

          .result-content {
            margin: 0;
            font-size: 12px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-all;
            color: var(--el-text-color-regular);
            max-height: 140px;
            overflow: hidden;
          }
        }
      }
    }

    .table-card {
      .table-title {
        cursor: default;

        &.is-stale-text {
          color: var(--el-color-warning);
        }
      }

      .pagination-row {
        display: flex;
        justify-content: flex-end;
        margin-top: 10px;
      }
    }
  }
</style>
