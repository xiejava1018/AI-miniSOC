import { describe, it, expect } from 'vitest'

describe('Users Page Component', () => {
  it('should be importable', async () => {
    const module = await import('@/views/system/Users.vue')
    expect(module.default).toBeDefined()
  })

  it('should export component as default', async () => {
    const module = await import('@/views/system/Users.vue')
    expect(typeof module.default).toBe('object')
  })
})
