import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue()], server: { watch: { usePolling: true }, allowedHosts: ['localhost', 'frontend'], proxy: { '/api': 'http://api:8000' } } })
