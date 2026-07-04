import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev: `npm run dev` proxies API/WS to the backend (default: robot on the LAN).
// Override with VITE_BACKEND=http://localhost:8080 for a local backend.
const backend = process.env.VITE_BACKEND ?? 'http://10.193.235.119:8080'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/ws': { target: backend, ws: true, changeOrigin: true },
    },
  },
  build: { chunkSizeWarningLimit: 700 },
})
