import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // the static build is served from any sub-path (GitHub Pages, Cloudflare Pages), so use relative asset URLs
  base: mode === 'static' ? './' : '/',
  worker: { format: 'es' },
  server: {
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    fs: { allow: ['..'] },          // the static build bundles ../backend/windtunnel/*.py
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8765', ws: true },
    },
  },
  build: { outDir: mode === 'static' ? 'dist-static' : 'dist', sourcemap: false },
}))
