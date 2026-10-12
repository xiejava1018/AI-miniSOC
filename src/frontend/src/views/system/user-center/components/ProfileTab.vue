<!-- 基本资料 Tab：可编辑 nick_name/phone/email/avatar/gender；username/role/department 只读 -->
<template>
  <ElForm
    ref="formRef"
    :model="form"
    class="profile-form"
    :rules="rules"
    label-width="86px"
    label-position="top"
    @submit.prevent
  >
    <ElRow>
      <ElFormItem label="用户名（不可改）">
        <ElInput :model-value="profile.username" disabled />
      </ElFormItem>
      <ElFormItem label="角色（不可改）" class="ml-5">
        <ElInput :model-value="profile.role_name || profile.role_code || '-'" disabled />
      </ElFormItem>
    </ElRow>
    <ElRow>
      <ElFormItem label="部门（不可改）">
        <ElInput :model-value="profile.department_name || '-'" disabled />
      </ElFormItem>
      <ElFormItem label="昵称" prop="nick_name" class="ml-5">
        <ElInput
          v-model="form.nick_name"
          :disabled="!isEdit"
          maxlength="100"
          placeholder="请输入昵称"
        />
      </ElFormItem>
    </ElRow>
    <ElRow>
      <ElFormItem label="手机" prop="phone">
        <ElInput
          v-model="form.phone"
          :disabled="!isEdit"
          maxlength="20"
          placeholder="请输入手机号"
        />
      </ElFormItem>
      <ElFormItem label="邮箱" prop="email" class="ml-5">
        <ElInput
          v-model="form.email"
          :disabled="!isEdit"
          maxlength="100"
          placeholder="请输入邮箱"
        />
      </ElFormItem>
    </ElRow>
    <ElRow>
      <ElFormItem label="性别">
        <ElRadioGroup v-model="form.gender" :disabled="!isEdit">
          <ElRadio :value="0">未设置</ElRadio>
          <ElRadio :value="1">男</ElRadio>
          <ElRadio :value="2">女</ElRadio>
        </ElRadioGroup>
      </ElFormItem>
      <ElFormItem label="头像 URL" prop="avatar" class="ml-5">
        <ElInput
          v-model="form.avatar"
          :disabled="!isEdit"
          maxlength="255"
          placeholder="https://…"
        />
      </ElFormItem>
    </ElRow>

    <div class="flex-c justify-end gap-3">
      <ElButton v-if="isEdit" @click="cancelEdit">取消</ElButton>
      <ElButton type="primary" :loading="saving" @click="toggleSave">
        {{ isEdit ? '保存' : '编辑' }}
      </ElButton>
    </div>
  </ElForm>
</template>

<script setup lang="ts">
  import { ElMessage } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'
  import { fetchUpdateMyProfile, type MyProfile } from '@/api/user-center'

  defineOptions({ name: 'ProfileTab' })

  const props = defineProps<{ profile: MyProfile }>()
  const emit = defineEmits<{ (e: 'saved', profile: MyProfile): void }>()

  const formRef = ref<FormInstance>()
  const isEdit = ref(false)
  const saving = ref(false)

  const form = reactive({
    nick_name: '',
    phone: '',
    email: '',
    avatar: '',
    gender: 0
  })

  /** 同步 props → 表单（进入页面 / 保存成功后） */
  const syncFromProfile = () => {
    form.nick_name = props.profile.nick_name || ''
    form.phone = props.profile.phone || ''
    form.email = props.profile.email || ''
    form.avatar = props.profile.avatar || ''
    form.gender = props.profile.gender ?? 0
  }

  watch(
    () => props.profile,
    () => {
      if (!isEdit.value) syncFromProfile()
    },
    { immediate: true }
  )

  const rules: FormRules = {
    email: [
      {
        pattern: /^$|^[\w.%+-]+@[\w.-]+\.[a-zA-Z]{2,}$/,
        message: '邮箱格式不正确',
        trigger: 'blur'
      }
    ],
    phone: [{ pattern: /^$|^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' }]
  }

  const cancelEdit = () => {
    syncFromProfile()
    isEdit.value = false
  }

  const toggleSave = async () => {
    if (!isEdit.value) {
      isEdit.value = true
      return
    }
    if (!formRef.value) return
    try {
      await formRef.value.validate()
    } catch {
      return
    }
    saving.value = true
    try {
      const latest = await fetchUpdateMyProfile({
        nick_name: form.nick_name || null,
        phone: form.phone || null,
        email: form.email || null,
        avatar: form.avatar || null,
        gender: form.gender
      })
      ElMessage.success('资料已更新')
      isEdit.value = false
      emit('saved', latest)
    } catch (e) {
      console.error('保存资料失败', e)
    } finally {
      saving.value = false
    }
  }
</script>

<style scoped lang="scss">
  .profile-form :deep(.el-row .el-form-item) {
    width: calc(50% - 10px);
  }

  .profile-form :deep(.el-row .el-form-item.ml-5) {
    margin-left: 20px;
  }
</style>
