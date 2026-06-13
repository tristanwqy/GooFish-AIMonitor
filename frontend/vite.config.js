import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 构建产物输出到 FastAPI 静态目录, 由后端直接 serve。
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../src/xianyu_crawler/web/static',
    emptyOutDir: true,
  },
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
