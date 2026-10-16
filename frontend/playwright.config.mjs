import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45000,
  reporter: 'list',
  outputDir: '../.local/browser-results',
  use: {
    baseURL: 'http://127.0.0.1:3100',
    launchOptions: { executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', args: ['--no-sandbox'] },
    screenshot: 'only-on-failure',
    trace: 'off',
  },
});
