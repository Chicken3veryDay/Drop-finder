import { test, expect } from '@playwright/test';

const appUrl = process.env.DROPFINDER_E2E_URL;

test.describe('DropFinder platform integration', () => {
  test.skip(!appUrl, 'DROPFINDER_E2E_URL must target the integrated issue #5/#8 application');

  test('keeps the marketplace DOM bounded during continuous scrolling', async ({ page }) => {
    await page.goto(appUrl);
    await page.getByRole('main').waitFor();
    for (let index = 0; index < 20; index += 1) await page.mouse.wheel(0, 1800);
    const rows = page.locator('[data-marketplace-row]');
    expect(await rows.count()).toBeLessThan(80);
    await expect(page.locator('[role="feed"]')).toHaveAttribute('aria-setsize', /\d+/);
  });

  test('cancels rapid searches and publishes only the latest result', async ({ page }) => {
    await page.goto(appUrl);
    const search = page.getByRole('searchbox');
    await search.pressSequentially('blue dream', { delay: 5 });
    await expect(page.locator('[data-query-version]')).toHaveAttribute('data-query-current', 'true');
  });

  test('opens a document, traps focus, closes with Escape, and restores focus', async ({ page }) => {
    await page.goto(appUrl);
    const opener = page.getByRole('button', { name: /open (coa|terpene)/i }).first();
    await opener.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await page.keyboard.press('Tab');
    await expect(dialog).toContainText(/page|open original/i);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(opener).toBeFocused();
  });

  test('reloads offline from the last complete generation', async ({ page, context }) => {
    await page.goto(appUrl);
    await page.waitForFunction(() => navigator.serviceWorker?.controller);
    await context.setOffline(true);
    await page.reload();
    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.locator('[data-generation-id]')).not.toHaveAttribute('data-generation-id', '');
  });
});
