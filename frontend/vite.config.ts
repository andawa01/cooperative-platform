import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Optional: proxy /api to the backend so we don't need CORS in dev.
    // We're using CORS instead so this stays commented.
    // proxy: { '/api': 'http://localhost:8000' },
  },
})