// The isolated branch has no issue #5 shell or issue #8 marketplace to launch.
// Run this after integration with: npx playwright test web/tests/e2e/platform.spec.mjs
try {
  await import('@playwright/test');
  console.error('Playwright is installed, but the integration app URL is intentionally not invented on this isolated branch.');
  process.exitCode = 2;
} catch {
  console.log('SKIP: Playwright is unavailable in the dependency-free isolated harness. Execute after issue #5/#8 integration.');
}
