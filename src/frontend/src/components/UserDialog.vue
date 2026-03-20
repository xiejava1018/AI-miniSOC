<template>
  <el-dialog
    :model-value="modelValue"
    :title="mode === 'create' ? '创建用户' : '编辑用户'"
    width="600px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="100px"
    >
      <el-form-item label="用户名" prop="username">
        <el-input
          v-model="formData.username"
          :disabled="mode === 'edit'"
          placeholder="请输入用户名（3-50字符）"
        />
      </el-form-item>

      <el-form-item label="密码" prop="password" v-if="mode === 'create'">
        <el-input
          v-model="formData.password"
          type="password"
          placeholder="请输入密码（至少6位）"
          show-password
        />
      </el-form-item>

      <el-form-item label="邮箱" prop="email">
        <el-input
          v-model="formData.email"
          type="email"
          placeholder="请输入邮箱"
        />
      </el-form-item>

      <el-form-item label="姓名" prop="full_name">
        <el-input
          v-model="formData.full_name"
          placeholder="请输入姓名"
        />
      </el-form-item>

      <el-form-item label="手机号" prop="phone">
        <el-input
          v-model="formData.phone"
          placeholder="请输入手机号"
        />
      </el-form-item>

      <el-form-item label="部门" prop="department">
        <el-input
          v-model="formData.department"
          placeholder="请输入部门"
        />
      </el-form-item>

      <el-form-item label="角色" prop="role_id">
        <el-select
          v-model="formData.role_id"
          placeholder="请选择角色"
          style="width: 100%"
        >
          <el-option
            v-for="role in roles"
            :key="role.id"
            :label="role.name"
            :value="role.id"
          />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button
        type="primary"
        @click="handleSubmit"
        :loading="submitting"
      >
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { User, UserCreate, UserUpdate, Role } from '@/types/user'

interface Props {
  modelValue: boolean
  user?: User
  roles: Role[]
  mode: 'create' | 'edit'
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'submit': [data: UserCreate | UserUpdate]
}>()

const formRef = ref<FormInstance>()
const submitting = ref(false)

const formData = reactive<{
  username: string
  password: string
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id?: number
}>({
  username: '',
  password: '',
  email: '',
  full_name: '',
  phone: '',
  department: '',
  role_id: undefined
})

const formRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度在3-50个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度在6-100个字符', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' }
  ],
  role_id: [
    { required: true, message: '请选择角色', trigger: 'change' }
  ]
}

// 监听用户数据变化，填充表单
watch(() => props.user, (user) => {
  if (user && props.mode === 'edit') {
    formData.username = user.username
    formData.email = user.email
    formData.full_name = user.full_name
    formData.phone = user.phone
    formData.department = user.department
    formData.role_id = user.role_id
  }
}, { immediate: true })

// 监听对话框关闭，重置表单
watch(() => props.modelValue, (visible) => {
  if (!visible) {
    formRef.value?.resetFields()
  }
})

function handleCancel() {
  emit('update:modelValue', false)
}

async function handleSubmit() {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      if (props.mode === 'create') {
        const data: UserCreate = {
          username: formData.username,
          password: formData.password,
          email: formData.email,
          full_name: formData.full_name,
          phone: formData.phone,
          department: formData.department,
          role_id: formData.role_id!
        }
        emit('submit', data)
      } else {
        const data: UserUpdate = {
          email: formData.email,
          full_name: formData.full_name,
          phone: formData.phone,
          department: formData.department,
          role_id: formData.role_id
        }
        emit('submit', data)
      }
    } finally {
      submitting.value = false
    }
  })
}
</script>

<style scoped>
.el-form {
  padding: 0 20px;
}
</style>
