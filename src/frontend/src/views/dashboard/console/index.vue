<!-- 工作台页面 -->
<template>
  <div>
    <CardList></CardList>

    <el-row :gutter="20">
      <el-col :sm="24" :md="12" :lg="10">
        <ActiveUser />
      </el-col>
      <el-col :sm="24" :md="12" :lg="14">
        <SalesOverview />
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :sm="24" :md="12" :lg="12">
        <Dynamic />
      </el-col>
      <el-col :sm="24" :md="12" :lg="12">
        <TodoList />
      </el-col>
    </el-row>

    <!-- SOC 资产健康度(末尾追加,不破坏原 6 个模块) -->
    <AssetHealth />

    <AboutProject />
  </div>
</template>

<script setup lang="ts">
  import CardList from './modules/card-list.vue'
  import ActiveUser from './modules/active-user.vue'
  import SalesOverview from './modules/sales-overview.vue'
  import Dynamic from './modules/dynamic-stats.vue'
  import TodoList from './modules/todo-list.vue'
  import AssetHealth from './modules/asset-health.vue'
  import AboutProject from './modules/about-project.vue'

  defineOptions({ name: 'Console' })
</script>
