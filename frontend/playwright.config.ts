import { defineConfig } from '@playwright/test'

// Smoke test against the running app (backend :8765 + Vite :5180). Starts `npm run dev` if nothing is listening.
export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:5180', headless: true, viewport: { width: 1440, height: 900 } },
  webServer: { command: 'npm run dev', url: 'http://127.0.0.1:5180', reuseExistingServer: true, timeout: 120_000 },
  reporter: 'list',
})
