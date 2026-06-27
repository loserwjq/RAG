import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        timeout: 600000,      // 10 分钟—匹配网关解析超时
        proxyTimeout: 600000,  // 10 分钟—等待响应完成
      },
    },
  },
})
