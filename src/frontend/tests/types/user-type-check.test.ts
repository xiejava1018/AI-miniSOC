// This file tests type definitions by using them
// Type errors will be caught by TypeScript compiler
import type {
  User,
  UserCreate,
  UserUpdate,
  Role,
  UserListResponse,
  ResetPasswordRequest,
  LockUserRequest
} from '@/types/user'

// Test User type
const user: User = {
  id: 1,
  username: 'testuser',
  email: 'test@example.com',
  full_name: 'Test User',
  role_id: 1,
  status: 'active',
  is_locked: false,
  created_at: '2026-03-20T10:00:00Z',
  updated_at: '2026-03-20T10:00:00Z'
}

// Test UserCreate type
const userCreate: UserCreate = {
  username: 'newuser',
  password: 'Password123',
  email: 'new@example.com',
  role_id: 1
}

// Test UserUpdate type
const userUpdate: UserUpdate = {
  email: 'updated@example.com',
  full_name: 'Updated Name'
}

// Test Role type
const role: Role = {
  id: 1,
  name: 'Admin',
  code: 'admin',
  is_system: true
}

// Test UserListResponse type
const userList: UserListResponse = {
  total: 1,
  page: 1,
  page_size: 20,
  items: [user]
}

// Test request types
const resetRequest: ResetPasswordRequest = {
  new_password: 'NewPass123'
}

const lockRequest: LockUserRequest = {
  is_locked: true,
  lock_reason: 'Test reason'
}

export {
  user,
  userCreate,
  userUpdate,
  role,
  userList,
  resetRequest,
  lockRequest
}
