import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

/**
 * OH-Q.2 前端测试体系（vitest）
 *
 * 独立于 vite.config.ts：构建配置含 AutoImport/Components 等重插件，
 * 测试环境保持轻量——组件内用到的 Element Plus 走全局 stub 或真实挂载。
 */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/utils/**', 'src/directives/**'],
      exclude: ['src/**/*.d.ts'],
    },
  },
})
