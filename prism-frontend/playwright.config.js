import { defineConfig } from '@playwright/test';
import process from 'node:process';
const apiPort = process.env.PRISM_DEMO_PORT || '8000';
const uiPort = process.env.PRISM_TEST_UI_PORT || '5173';
export default defineConfig({
  testDir: './e2e', workers: 1, timeout: 180000,
  expect: { timeout: 20000 },
  use: { baseURL: `http://127.0.0.1:${uiPort}`, viewport: { width: 1400, height: 1000 } },
  reporter: [['list']],
  webServer: [
    { command: 'node scripts/demo-backend.mjs', url: `http://127.0.0.1:${apiPort}/health`, reuseExistingServer: process.env.PRISM_REUSE_DEMO === 'true', timeout: 60000 },
    { command: `npm run dev -- --host 127.0.0.1 --port ${uiPort} --strictPort`, url: `http://127.0.0.1:${uiPort}`, reuseExistingServer: process.env.PRISM_REUSE_DEMO === 'true', timeout: 60000,
      env: { VITE_API_URL: `http://127.0.0.1:${apiPort}`, VITE_PRISM_DEMO_FIXTURES: 'true' } },
  ],
});
