import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // ⚠️ 生产构建由后端挂载在子路径 /app/ 下，
  // 必须设 base 让资源引用带上 /app 前缀，否则 /assets/*.js 会 404 → 页面白屏
  base: '/app/',
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // 开发时把 /api 转发到后端，避免跨域
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
