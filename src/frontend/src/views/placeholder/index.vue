<template>
  <div class="placeholder-page">
    <div class="content">
      <el-empty description="功能开发中">
        <template #image>
          <div class="icon-wrap">
            <el-icon :size="64" color="#909399"><Tools /></el-icon>
          </div>
        </template>
        <p class="desc">该功能正在开发中，敬请期待</p>
        <el-button type="primary" @click="$router.back()">返回</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { Tools } from '@element-plus/icons-vue'
  defineOptions({ name: 'PlaceholderPage' })
</script>

<style scoped lang="scss">
  .placeholder-page {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 400px;

    .content {
      text-align: center;
    }

    .icon-wrap {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 120px;
      height: 120px;
      margin: 0 auto 20px;
      background: var(--art-gray-100);
      border-radius: 50%;
    }

    .desc {
      margin-top: 8px;
      font-size: 14px;
      color: var(--art-text-gray);
    }
  }
</style>
