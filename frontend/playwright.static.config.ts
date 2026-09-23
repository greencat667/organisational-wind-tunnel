import { defineConfig } from '@playwright/test'

// End-to-end test of the static build (`npm run build:static`): the simulation runs in the browser, no Python server.
// Needs network access to the Pyodide CDN on first run.
export default defineConfig({
  testDir: './tests-static',
  timeout: 600_000,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:5182', headless: true, viewport: { width: 1440, height: 900 } },
  webServer: { command: 'npx vite preview --mode static --outDir dist-static --port 5182 --strictPort', url: 'http://127.0.0.1:5182', reuseExistingServer: true, timeout: 60_000 },
  reporter: 'list',
})
