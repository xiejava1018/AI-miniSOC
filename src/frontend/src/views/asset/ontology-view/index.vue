<!--
  本体对齐视图（OH-UI.8）

  展示资产本体的类如何对齐到平台数据：
    - KPI：ORM 映射类 / 图谱节点类 / 未映射类
    - 类对齐表：每类的映射形态、表/filter、实例计数（ORM）、图谱节点
    - 完整性校验：未解析模型 / 未知列
  只读视图，不修改数据；图谱节点类无 SQL 计数，显式「—」而非 0。
-->
<template>
  <div class="ontology-view" v-loading="loading">
    <!-- KPI -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-num">{{ align.orm_class_count }}</div>
        <div class="kpi-label">映射到数据表的类</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-num">{{ align.graph_class_count }}</div>
        <div class="kpi-label">映射到图谱节点的类</div>
      </div>
      <div class="kpi-card" :class="{ alert: align.unmapped_count > 0 }">
        <div class="kpi-num">{{ align.unmapped_count }}</div>
        <div class="kpi-label">未映射的类</div>
      </div>
    </div>

    <ElCard shadow="never" class="panel">
      <template #header>
        <div class="card-head">
          <span class="panel-title">类对齐总览</span>
          <ElButton text @click="load">
            <ElIcon><Refresh /></ElIcon>刷新
          </ElButton>
        </div>
      </template>

      <ElTable :data="align.classes" table-layout="fixed" row-key="class_id">
        <ElTableColumn prop="label" label="本体类" min-width="160">
          <template #default="{ row }">
            <div class="class-label">{{ row.label }}</div>
            <div class="class-id">{{ row.class_id }}</div>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="mapped_to" label="映射形态" width="120">
          <template #default="{ row }">
            <ElTag :type="mapTag[row.mapped_to]">
              {{ mapLabel[row.mapped_to] }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="数据表 / 模型" min-width="170">
          <template #default="{ row }">
            <template v-if="row.mapped_to === 'orm'">
              <code class="tbl">{{ row.table }}</code>
              <span class="muted"> ({{ row.model_name }})</span>
            </template>
            <template v-else-if="row.mapped_to === 'graph'">
              <ElTag v-for="t in row.graph_node_types" :key="t"
                      size="small" type="info" class="node-tag">{{ t }}</ElTag>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="实例计数" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.instance_count != null" class="count">
              {{ row.instance_count }}
            </span>
            <span v-else class="muted">—</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="过滤条件 / 备注" min-width="200">
          <template #default="{ row }">
            <code v-if="row.filter" class="filter">{{ row.filter }}</code>
            <span v-if="row.planned && row.planned.length" class="planned-note">
              规划中（尚未落地）：{{ row.planned.join(', ') }}
            </span>
            <span v-if="row.unresolved && row.unresolved.length" class="unresolved">
              <ElIcon><WarningFilled /></ElIcon>
              未注册模型：{{ row.unresolved.join(', ') }}
            </span>
            <span v-if="!row.filter && !(row.unresolved && row.unresolved.length)"
                  class="muted">—</span>
          </template>
        </ElTableColumn>
      </ElTable>
      <div class="red-line">{{ align.red_line }}</div>
    </ElCard>

    <!-- 完整性校验 -->
    <ElCard shadow="never" class="panel">
      <template #header>
        <div class="card-head">
          <span class="panel-title">映射完整性校验</span>
          <ElTag size="small" :type="validation.valid ? 'success' : 'danger'">
            {{ validation.valid ? '通过' : `${validation.problems.length} 个问题` }}
          </ElTag>
        </div>
      </template>

      <ElEmpty v-if="validation.valid" description="所有映射引用均可解析"
               :image-size="70" />
      <ElTable v-else :data="validation.problems" table-layout="fixed" size="small">
        <ElTableColumn prop="class_id" label="本体类" width="180"
                      show-overflow-tooltip />
        <ElTableColumn prop="kind" label="问题类型" width="150">
          <template #default="{ row }">
            <ElTag size="small" type="warning">{{ problemLabel[row.kind] }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="detail" label="详情" min-width="220"
                      show-overflow-tooltip />
      </ElTable>
      <div class="muted meta">共校验 {{ validation.checked_classes }} 个类</div>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Refresh, WarningFilled } from '@element-plus/icons-vue'
import {
  getOntologyAlignment,
  validateOntology,
  type OntologyAlignment,
  type OntologyValidateResult,
} from '@/api/ontology'

defineOptions({ name: 'AssetOntologyView' })

const loading = ref(false)
const align = reactive<OntologyAlignment>({
  classes: [],
  orm_class_count: 0,
  graph_class_count: 0,
  unmapped_count: 0,
  red_line: '',
})
const validation = reactive<OntologyValidateResult>({
  valid: true,
  problems: [],
  checked_classes: 0,
})

const mapLabel: Record<string, string> = {
  orm: '数据表', graph: '图谱节点', unmapped: '未映射',
}
const mapTag: Record<string, any> = {
  orm: 'success', graph: 'info', unmapped: 'danger',
}
const problemLabel: Record<string, string> = {
  unresolved_model: '模型未注册',
  unknown_column: '未知列',
}

async function load() {
  loading.value = true
  try {
    const [a, v] = await Promise.all([
      getOntologyAlignment(),
      validateOntology(),
    ])
    Object.assign(align, a)
    Object.assign(validation, v)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.kpi-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.kpi-card {
  flex: 1;
  min-width: 170px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 16px 20px;
}
.kpi-card.alert {
  border-color: var(--el-color-danger-light-5);
}
.kpi-num {
  font-size: 28px;
  font-weight: 600;
}
.kpi-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 4px;
}
.panel {
  margin-bottom: 12px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  font-weight: 600;
}
.class-label {
  font-weight: 500;
}
.class-id {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
.tbl {
  background: var(--el-fill-color-light);
  padding: 1px 5px;
  border-radius: 3px;
}
.node-tag {
  margin-right: 4px;
}
.count {
  font-weight: 600;
}
.filter {
  font-size: 12px;
  background: var(--el-fill-color-light);
  padding: 1px 5px;
  border-radius: 3px;
}
.unresolved {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--el-color-danger);
  font-size: 12px;
}
.planned-note {
  color: var(--el-color-info);
  font-size: 12px;
}
.muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.red-line {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 10px;
}
.meta {
  margin-top: 8px;
}
</style>
