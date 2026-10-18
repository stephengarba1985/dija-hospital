import { test, expect } from '@playwright/test';
import fs from 'node:fs';

test('account controls stay reachable on short, narrow and zoomed layouts', async ({ page }) => {
  const credentials = JSON.parse(fs.readFileSync('../.local/admin-login.json', 'utf8'));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username);
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign in to workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Hospital overview.' })).toBeVisible();
  const header = page.locator('.topbar');
  const signOut = header.getByRole('button', { name: 'Sign out', exact: true });
  for (const [width, height] of [[1366,600],[1024,600],[682,300],[390,600],[320,568]]) {
    await page.setViewportSize({ width, height });
    await expect(signOut).toBeInViewport({ ratio: 1 });
    await expect(header.locator('.topbar-username')).toBeInViewport({ ratio: 1 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect(signOut).toBeInViewport({ ratio: 1 });
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  await page.getByRole('button', { name: 'Open navigation' }).click();
  const sidebarAccount = page.locator('.sidebar .user-card');
  await sidebarAccount.scrollIntoViewIfNeeded();
  await expect(sidebarAccount).toBeInViewport({ ratio: 1 });
  await page.getByRole('button', { name: 'Close navigation' }).click({ position: { x: 290, y: 100 } });
  await signOut.click();
  await expect(page.getByRole('button', { name: 'Sign in to workspace' })).toBeVisible();
  expect((await page.request.get('/api/patients/')).status()).toBe(401);
});
