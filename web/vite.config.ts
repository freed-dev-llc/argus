import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server proxies API + health calls to the Argus FastAPI server on :8080.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
    },
  },
})
