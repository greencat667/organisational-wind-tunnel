import { defineConfig } from '@playwright/test'

// Regenerates the screenshots in docs/images/ used by docs/GUIDE.md: `npm run docs:screenshots`.
// Drives the real app (backend :8765 + Vite :5180), like the smoke test; starts `npm run dev` if nothing is listening.
export default defineConfig({
  testDir: './docs-shots',
  timeout: 300_000,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:5180', headless: true, viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
  webServer: { command: 'npm run dev', url: 'http://127.0.0.1:5180', reuseExistingServer: true, timeout: 120_000 },
  reporter: 'list',
})
