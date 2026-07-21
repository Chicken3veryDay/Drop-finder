import { test, expect } from '@playwright/test';

const EXPECTED_GENERATION = process.env.EXPECTED_GENERATION;
if (!EXPECTED_GENERATION) throw new Error('EXPECTED_GENERATION is required');

async function readGenerationStatus(page) {
  return page.evaluate(async () => {
    const controller = navigator.serviceWorker?.controller;
    if (!controller) return null;
    return new Promise(resolve => {
      const timer = setTimeout(() => {
        navigator.serviceWorker.removeEventListener('message', onMessage);
        resolve(null);
      }, 2_000);
      function onMessage(event) {
        if (event.data?.type !== 'generation-status') return;
        clearTimeout(timer);
        navigator.serviceWorker.removeEventListener('message', onMessage);
        resolve(event.data?.id ?? null);
      }
      navigator.serviceWorker.addEventListener('message', onMessage);
      controller.postMessage({ type: 'generation-status' });
    });
  });
}

test('fresh public worker activates the current immutable generation', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  await page.addInitScript(() => {
    window.__generationMessages = [];
    navigator.serviceWorker?.addEventListener('message', event => {
      window.__generationMessages.push(event.data);
    });
  });

  const nonce = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  await page.goto(`./?activation_v5b=${nonce}`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => navigator.serviceWorker.ready);
  if (!(await page.evaluate(() => Boolean(navigator.serviceWorker.controller)))) {
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  }

  const release = await page.evaluate(async token => {
    const [workerResponse, manifestResponse, runtimeResponse] = await Promise.all([
      fetch(`./sw.js?activation_v5b=${token}`, { cache: 'no-store' }),
      fetch(`./data/catalog-v4/manifest.json?activation_v5b=${token}`, { cache: 'no-store' }),
      fetch(`./data/runtime.json?activation_v5b=${token}`, { cache: 'no-store' }),
    ]);
    if (!workerResponse.ok || !manifestResponse.ok || !runtimeResponse.ok) {
      throw new Error(`release fetch failed: ${workerResponse.status}/${manifestResponse.status}/${runtimeResponse.status}`);
    }
    return {
      worker: await workerResponse.text(),
      manifest: await manifestResponse.json(),
      runtime: await runtimeResponse.json(),
    };
  }, nonce);

  expect(release.worker).toContain('prepared-generations/');
  expect(release.worker).toContain('activationSequence');
  expect(release.manifest.generation_id).toBe(EXPECTED_GENERATION);
  expect(release.runtime.status).toBe('healthy');
  expect(release.runtime.zero_degraded_active_services).toBe(true);

  await expect.poll(() => readGenerationStatus(page), {
    timeout: 60_000,
    intervals: [250, 500, 1_000, 2_000],
  }).toBe(EXPECTED_GENERATION);

  await expect(page.locator('main')).toBeVisible();
  const results = page.getByRole('list', {
    name: new RegExp(`^${release.manifest.product_count} marketplace results$`, 'i'),
  });
  await expect(results).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('body')).not.toContainText('Catalog generation activation failed');

  const messages = await page.evaluate(() => window.__generationMessages ?? []);
  const terminalErrors = messages.filter(message => (
    message?.type === 'generation-error'
    && message?.generationId === EXPECTED_GENERATION
    && message?.code !== 'generation_incomplete'
  ));
  expect(terminalErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
