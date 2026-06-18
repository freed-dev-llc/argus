import { readFileSync } from 'node:fs'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Single-source the app version from package.json (exposed to the app as __APP_VERSION__).
const { version } = JSON.parse(
  readFileSync(new URL('./package.json', import.meta.url), 'utf-8'),
) as { version: string }

// Dev server proxies API + health calls to the Argus FastAPI server on :8080.
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
    },
  },
})
