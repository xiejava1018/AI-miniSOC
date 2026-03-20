import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUsersStore } from '@/stores/users'
import type { User, UserCreate, UserUpdate } from '@/types/user'

// Mock API call
const mockApiCall = vi.fn()
vi.mock('@/api', () => ({
  apiCall: () => mockApiCall()
}))

describe('Users Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('Initial State', () => {
    it('should have correct initial state', () => {
      const store = useUsersStore()

      expect(store.users).toEqual([])
      expect(store.loading).toBe(false)
      expect(store.pagination.page).toBe(1)
      expect(store.pagination.page_size).toBe(20)
      expect(store.pagination.total).toBe(0)
      expect(store.filters).toEqual({})
    })

    it('should calculate totalPages correctly', () => {
      const store = useUsersStore()

      store.pagination.total = 0
      expect(store.totalPages).toBe(0)

      store.pagination.total = 20
      store.pagination.page_size = 20
      expect(store.totalPages).toBe(1)

      store.pagination.total = 50
      store.pagination.page_size = 20
      expect(store.totalPages).toBe(3)
    })
  })

  describe('Filters', () => {
    it('should reset filters correctly', () => {
      const store = useUsersStore()

      store.filters.search = 'test'
      store.filters.role_id = 1
      store.filters.status = 'active'
      store.pagination.page = 5

      store.resetFilters()

      expect(store.filters.search).toBeUndefined()
      expect(store.filters.role_id).toBeUndefined()
      expect(store.filters.status).toBeUndefined()
      expect(store.pagination.page).toBe(1)
    })
  })

  describe('API Actions', () => {
    it('should fetch users successfully', async () => {
      const mockUsers: User[] = [
        {
          id: 1,
          username: 'testuser',
          role_id: 1,
          status: 'active',
          is_locked: false,
          created_at: '2026-03-20T10:00:00Z',
          updated_at: '2026-03-20T10:00:00Z'
        }
      ]

      mockApiCall.mockResolvedValue({
        total: 1,
        page: 1,
        page_size: 20,
        items: mockUsers
      })

      const store = useUsersStore()
      await store.fetchUsers()

      expect(store.users).toEqual(mockUsers)
      expect(store.pagination.total).toBe(1)
      expect(store.loading).toBe(false)
    })

    it('should handle fetchUsers error', async () => {
      mockApiCall.mockRejectedValue(new Error('Network error'))

      const store = useUsersStore()

      await expect(store.fetchUsers()).rejects.toThrow('Network error')
      expect(store.loading).toBe(false)
    })

    it('should create user successfully', async () => {
      const newUser: User = {
        id: 2,
        username: 'newuser',
        role_id: 1,
        status: 'active',
        is_locked: false,
        created_at: '2026-03-20T10:00:00Z',
        updated_at: '2026-03-20T10:00:00Z'
      }

      mockApiCall.mockResolvedValue(newUser)

      const store = useUsersStore()
      const userData: UserCreate = {
        username: 'newuser',
        password: 'Password123',
        role_id: 1
      }

      const result = await store.createUser(userData)

      expect(result).toEqual(newUser)
      expect(store.loading).toBe(false)
    })

    it('should update user successfully', async () => {
      const updatedUser: User = {
        id: 1,
        username: 'testuser',
        email: 'updated@example.com',
        role_id: 1,
        status: 'active',
        is_locked: false,
        created_at: '2026-03-20T10:00:00Z',
        updated_at: '2026-03-20T10:00:00Z'
      }

      mockApiCall.mockResolvedValue(updatedUser)

      const store = useUsersStore()
      const updateData: UserUpdate = {
        email: 'updated@example.com'
      }

      const result = await store.updateUser(1, updateData)

      expect(result.email).toBe('updated@example.com')
      expect(store.loading).toBe(false)
    })

    it('should delete user successfully', async () => {
      mockApiCall.mockResolvedValue({ success: true })

      const store = useUsersStore()

      await expect(store.deleteUser(1)).resolves.not.toThrow()
      expect(store.loading).toBe(false)
    })

    it('should reset password successfully', async () => {
      mockApiCall.mockResolvedValue({
        new_password: 'NewPass123'
      })

      const store = useUsersStore()

      const newPassword = await store.resetPassword(1, 'NewPass123')

      expect(newPassword).toBe('NewPass123')
    })

    it('should reset password with auto-generation', async () => {
      const generatedPassword = 'Abc123!@#xyz'
      mockApiCall.mockResolvedValue({
        new_password: generatedPassword
      })

      const store = useUsersStore()

      const newPassword = await store.resetPassword(1)

      expect(newPassword).toBe(generatedPassword)
    })

    it('should toggle lock successfully', async () => {
      const lockedUser: User = {
        id: 1,
        username: 'testuser',
        role_id: 1,
        status: 'locked',
        is_locked: true,
        created_at: '2026-03-20T10:00:00Z',
        updated_at: '2026-03-20T10:00:00Z'
      }

      mockApiCall.mockResolvedValue(lockedUser)

      const store = useUsersStore()

      const result = await store.toggleLock(1, true, 'Test reason')

      expect(result.is_locked).toBe(true)
      expect(store.loading).toBe(false)
    })
  })
})
