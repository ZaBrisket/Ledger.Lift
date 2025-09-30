import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'apps/web/e2e',
  use: {
    headless: true,
    baseURL: 'http://localhost:3000',
  },
  webServer: [
    {
      command: 'pnpm -w netlify:dev',
      port: 9999,
      timeout: 120000,
      reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_API_URL: 'http://localhost:9999/api' },
    },
    {
      command: 'pnpm --filter web dev',
      port: 3000,
      timeout: 120000,
      reuseExistingServer: !process.env.CI,
    },
  ]
});
