<!-- 安全设置 Tab：修改密码（成功后强制登出）+ 登录安全信息只读展示 -->
<template>
  <div>
    <div class="art-card-sm mb-5">
      <h3 class="card-title">
        <ArtSvgIcon icon="ri:shield-keyhole-line" class="mr-1.5" />
        修改密码
      </h3>
      <ElForm
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="90px"
        class="max-w-96"
        @submit.prevent
      >
        <ElFormItem label="当前密码" prop="old_password">
          <ElInput
            v-model="form.old_password"
            type="password"
            show-password
            autocomplete="off"
            placeholder="请输入当前密码"
          />
        </ElFormItem>
        <ElFormItem label="新密码" prop="new_password">
          <ElInput
            v-model="form.new_password"
            type="password"
            show-password
            autocomplete="off"
            placeholder="至少 6 位"
          />
        </ElFormItem>
        <ElFormItem label="确认新密码" prop="confirm_password">
          <ElInput
            v-model="form.confirm_password"
            type="password"
            show-password
            autocomplete="off"
            placeholder="再次输入新密码"
          />
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" :loading="saving" @click="submit">确认修改</ElButton>
        </ElFormItem>
      </ElForm>
    </div>

    <div class="art-card-sm">
      <h3 class="card-title">
        <ArtSvgIcon icon="ri:time-line" class="mr-1.5" />
        登录安全信息
      </h3>
      <ElDescriptions :column="1" border class="max-w-96">
        <ElDescriptionsItem label="最后登录">
          {{ formatTime(profile.last_login) }}
        </ElDescriptionsItem>
        <ElDescriptionsItem label="账号创建于">
          {{ formatTime(profile.created_at) }}
        </ElDescriptionsItem>
        <ElDescriptionsItem label="账号状态">
          <ElTag
            :type="profile.status === 'active' ? 'success' : 'danger'"
            size="small"
            effect="light"
          >
            {{ profile.status === 'active' ? '正常' : profile.status || '-' }}
          </ElTag>
        </ElDescriptionsItem>
      </ElDescriptions>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'
  import { fetchChangeMyPassword, type MyProfile } from '@/api/user-center'
  import { useUserStore } from '@/store/modules/user'

  defineOptions({ name: 'SecurityTab' })

  defineProps<{ profile: MyProfile }>()

  const userStore = useUserStore()
  const formRef = ref<FormInstance>()
  const saving = ref(false)

  const form = reactive({
    old_password: '',
    new_password: '',
    confirm_password: ''
  })

  const rules: FormRules = {
    old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
    new_password: [
      { required: true, message: '请输入新密码', trigger: 'blur' },
      { min: 6, message: '新密码至少 6 位', trigger: 'blur' }
    ],
    confirm_password: [
      { required: true, message: '请再次输入新密码', trigger: 'blur' },
      {
        validator: (_rule: any, value: string, callback: (err?: Error) => void) => {
          if (value !== form.new_password) callback(new Error('两次输入的新密码不一致'))
          else callback()
        },
        trigger: 'blur'
      }
    ]
  }

  const formatTime = (t?: string | null): string => {
    if (!t) return '-'
    const d = new Date(t)
    if (Number.isNaN(d.getTime())) return t
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }

  const submit = async () => {
    if (!formRef.value) return
    try {
      await formRef.value.validate()
    } catch {
      return
    }
    saving.value = true
    try {
      await fetchChangeMyPassword({
        old_password: form.old_password,
        new_password: form.new_password
      })
      ElMessage.success('密码修改成功，请重新登录')
      // 后端已使旧会话失效策略联动——强制登出回登录页
      setTimeout(() => userStore.logOut(), 800)
    } catch (e) {
      // 旧密码错(401)/强度弱(422) 的业务提示由拦截器弹出
      console.error('修改密码失败', e)
    } finally {
      saving.value = false
    }
  }
</script>

<style scoped lang="scss">
  .card-title {
    padding-bottom: 12px;
    margin-bottom: 16px;
    font-size: 15px;
    font-weight: 500;
    border-bottom: 1px solid var(--art-border-color, #e4e7ed);
  }

  .art-card-sm {
    padding: 16px 20px;
  }
</style>
