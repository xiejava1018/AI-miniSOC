<template>
  <div class="browsing-blacklist-page art-full-height" id="table-full-screen">
    <ElCard shadow="never" class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" @refresh="refresh">
        <template #left>
          <ElButton type="primary" @click="showDialog">新增黑名单</ElButton>
        </template>
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        table-layout="fixed"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 10 }"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <!-- 新增弹窗 -->
    <ElDialog v-model="dialogVisible" title="新增黑名单域名" width="480px" :close-on-click-modal="false">
      <ElForm ref="formRef" :model="form" :rules="rules" label-width="100px">
        <ElFormItem label="域名" prop="domain">
          <ElInput v-model="form.domain" placeholder="支持通配符，如 *.evil.com" />
        </ElFormItem>
        <ElFormItem label="来源" prop="source">
          <ElSelect v-model="form.source" style="width: 100%">
            <ElOption label="手动" value="manual" />
            <ElOption label="威胁情报" value="threat_intel" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="备注">
          <ElInput v-model="form.reason" type="textarea" :rows="2" placeholder="可选" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取 消</ElButton>
        <ElButton type="primary" @click="handleSubmit">确 定</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, h } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import type { FormInstance } from 'element-plus'
  import { useTable } from '@/composables/useTable'
  import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
  import {
    getBrowsingBlacklist,
    addBrowsingBlacklist,
    deleteBrowsingBlacklist
  } from '@/api/browsing'

  const tableApi = useTable<any>({
    core: {
      apiFn: getBrowsingBlacklist,
      apiParams: { domain: '' },
      columnsFactory: () => [
        { prop: 'domain', label: '域名', align: 'left', showOverflowTooltip: true },
        { prop: 'source', label: '来源', align: 'center', width: 120,
          formatter: (r: any) => (r.source === 'manual' ? '手动' : '威胁情报') },
        { prop: 'reason', label: '备注', align: 'left', showOverflowTooltip: true,
          formatter: (r: any) => r.reason || '--' },
        { prop: 'created_at', label: '创建时间', align: 'center', width: 170,
          formatter: (r: any) => (r.created_at || '').replace('T', ' ').slice(0, 19) },
        { prop: 'operation', label: '操作', align: 'center', width: 100, fixed: 'right',
          formatter: (r: any) =>
            h(ArtButtonTable, { type: 'delete', onClick: () => handleDelete(r) }) }
      ]
    }
  })

  const {
    data, loading, columns, columnChecks, pagination,
    handleSizeChange, handleCurrentChange, refresh
  } = tableApi as any

  // 新增
  const dialogVisible = ref(false)
  const formRef = ref<FormInstance>()
  const form = reactive({ domain: '', source: 'manual', reason: '' })
  const rules = { domain: [{ required: true, message: '请输入域名', trigger: 'blur' }] }

  const showDialog = () => {
    form.domain = ''
    form.source = 'manual'
    form.reason = ''
    dialogVisible.value = true
  }

  const handleSubmit = async () => {
    if (!formRef.value) return
    await formRef.value.validate(async (valid) => {
      if (!valid) return
      try {
        const res = await addBrowsingBlacklist({ ...form })
        if (res.code === 200 || res.code === 201) {
          ElMessage.success('添加成功')
          dialogVisible.value = false
          refresh()
        } else {
          ElMessage.error(res.message || '添加失败')
        }
      } catch (e) {
        console.error(e)
        ElMessage.error('添加失败')
      }
    })
  }

  const handleDelete = (row: any) => {
    ElMessageBox.confirm(`确定删除黑名单 ${row.domain} 吗？`, '删除确认', { type: 'warning' })
      .then(async () => {
        try {
          const res = await deleteBrowsingBlacklist(row.id)
          if (res.code === 200 || res.code === 201) {
            ElMessage.success('删除成功')
            refresh()
          } else {
            ElMessage.error(res.message || '删除失败')
          }
        } catch (e) {
          console.error(e)
        }
      })
      .catch(() => {})
  }
</script>

<style lang="scss" scoped>
  .browsing-blacklist-page {
    display: flex;
    flex-direction: column;
  }
</style>
