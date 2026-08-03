<template>
  <div class="browsing-config-page art-full-height">
    <ElCard shadow="never">
      <template #header>
        <div class="card-header">
          <span>检测规则配置</span>
          <div>
            <ElButton type="warning" plain :loading="testing" @click="handleTest">规则试运行</ElButton>
            <ElButton type="primary" :loading="saving" @click="handleSave">保存配置</ElButton>
          </div>
        </div>
      </template>

      <ElTable :data="configList" border style="width: 100%">
        <ElTableColumn prop="key" label="配置项" width="200" />
        <ElTableColumn prop="description" label="说明" min-width="200" show-overflow-tooltip />
        <ElTableColumn label="当前值" width="320">
          <template #default="{ row }">
            <ElInput v-if="isLongText(row)" v-model="row.value" type="textarea" :rows="2" />
            <ElInputNumber
              v-else-if="row.value_type === 'int'"
              v-model="row.value"
              :controls="false"
              style="width: 100%"
            />
            <ElSwitch
              v-else-if="row.value_type === 'bool'"
              :model-value="row.value === 'true'"
              @update:model-value="(v: any) => (row.value = String(v))"
            />
            <ElInput v-else v-model="row.value" />
          </template>
        </ElTableColumn>
        <ElTableColumn prop="value_type" label="类型" width="80" align="center" />
      </ElTable>
    </ElCard>

    <!-- 试运行结果 -->
    <ElDialog v-model="testResultVisible" title="规则试运行结果" width="780px">
      <div v-if="testResult" class="test-result">
        <ElAlert :title="`拉取 ${testResult.stats.fetched} 条 → 解析 ${testResult.stats.parsed} 条 → 发现 ${testResult.stats.findings} 个异常`"
          type="info" :closable="false" style="margin-bottom: 12px" />
        <ElTable :data="testResult.findings" border size="small" max-height="400">
          <ElTableColumn prop="ip" label="IP" width="130" />
          <ElTableColumn prop="domain" label="域名" show-overflow-tooltip />
          <ElTableColumn prop="score" label="分值" width="70" />
          <ElTableColumn prop="severity" label="等级" width="80">
            <template #default="{ row }">
              <ElTag :type="row.severity === 'critical' ? 'danger' : row.severity === 'high' ? 'danger' : row.severity === 'medium' ? 'warning' : 'info'">
                {{ row.severity }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="规则" width="120">
            <template #default="{ row }">
              {{ (row.rule_hits || []).map((h: any) => h.rule).join(',') }}
            </template>
          </ElTableColumn>
        </ElTable>
      </div>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, onMounted } from 'vue'
  import { ElMessage } from 'element-plus'
  import { getBrowsingRulesConfig, updateBrowsingRulesConfig, testBrowsingRules } from '@/api/browsing'

  const configList = ref<any[]>([])
  const saving = ref(false)
  const testing = ref(false)
  const testResultVisible = ref(false)
  const testResult = ref<any>(null)

  const loadConfig = async () => {
    try {
      const res = await getBrowsingRulesConfig()
      configList.value = (res?.data?.configs || []).map((c: any) => ({ ...c }))
    } catch (e) {
      console.error(e)
      ElMessage.error('加载配置失败')
    }
  }

  const isLongText = (row: any) => {
    const longKeys = ['tunnel_keywords', 'blacklist_domains', 'whitelist_domains', 'whitelist_ips', 'rules_enabled', 'notify_user_ids']
    return longKeys.includes(row.key)
  }

  const handleSave = async () => {
    saving.value = true
    try {
      const payload: Record<string, any> = {}
      configList.value.forEach((c) => {
        payload[c.key] = c.value
      })
      const res = await updateBrowsingRulesConfig(payload)
      if (res.code === 200 || res.code === 201) {
        ElMessage.success(`已更新 ${res.data?.updated || 0} 项配置`)
      } else {
        ElMessage.error(res.message || '保存失败')
      }
    } catch (e) {
      console.error(e)
      ElMessage.error('保存失败')
    } finally {
      saving.value = false
    }
  }

  const handleTest = async () => {
    testing.value = true
    try {
      const res = await testBrowsingRules(60)
      if (res.code === 200 || res.code === 201) {
        testResult.value = res.data
        testResultVisible.value = true
      } else {
        ElMessage.error(res.message || '试运行失败')
      }
    } catch (e) {
      console.error(e)
      ElMessage.error('试运行失败')
    } finally {
      testing.value = false
    }
  }

  onMounted(() => {
    loadConfig()
  })
</script>

<style lang="scss" scoped>
  .browsing-config-page {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .test-result {
      margin-top: 8px;
    }
  }
</style>
