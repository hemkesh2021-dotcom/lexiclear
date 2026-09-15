import { defineConfig, devices } from '@playwright/test';

// Some CI images ship a Chromium build that Playwright's own version pin does
// not match. Pointing at it is cheaper and more reproducible than downloading
// a second copy; unset, Playwright uses its managed browser as usual.
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH;
const launchOptions = executablePath ? { launchOptions: { executablePath } } : {};

/**
 * End-to-end configuration.
 *
 * The suite runs against the production Docker image with the mock model
 * provider enabled, so the journey under test is the one users get, executed
 * without an API key and without a network call to a model.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], ...launchOptions } },
    { name: 'mobile', use: { ...devices['Pixel 7'], ...launchOptions } },
  ],
});
