'use strict';

const fs = require('fs');
const { chromium } = require('playwright');

const URL = process.env.DROPFINDER_STATIC_URL || 'https://cgptmichaccount-dropfinder-os.static.hf.space';
const OUTPUT = process.env.DROPFINDER_BROWSER_REPORT || 'deployment/static-browser-verification.json';

function writeReport(report) {
  fs.mkdirSync(require('path').dirname(OUTPUT), { recursive: true });
  fs.writeFileSync(OUTPUT, JSON.stringify(report, null, 2) + '\n');
}

(async () => {
  let browser;
  let stage = 'launch';
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
      serviceWorkers: 'block'
    });
    const page = await context.newPage();
    const consoleErrors = [];
    const pageErrors = [];
    let imageRequests = 0;
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', error => pageErrors.push(String(error)));
    page.on('request', request => {
      if (request.resourceType() === 'image') imageRequests += 1;
    });
    await page.addInitScript(() => {
      window.__longTasks = [];
      try {
        new PerformanceObserver(list => {
          for (const entry of list.getEntries()) window.__longTasks.push(entry.duration);
        }).observe({ type: 'longtask', buffered: true });
      } catch (_) {}
    });

    stage = 'navigate';
    const navigationStarted = Date.now();
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 120000 });
    stage = 'initial_render';
    await page.waitForFunction(
      () => document.querySelector('#grid')?.dataset.renderComplete === 'true',
      null,
      { timeout: 30000 }
    );
    const readyMs = Date.now() - navigationStarted;
    const cardCount = await page.locator('.card').count();
    const resultText = await page.locator('#resultCount').innerText();
    const names = await page.locator('.card .name').allInnerTexts();
    const ids = await page.locator('.card').evaluateAll(cards => cards.map(card => card.dataset.productId));
    const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
    const paginationControls = await page.locator(
      '[class*="pagination"], [id*="pagination"], [data-page], button:has-text("Load more")'
    ).count();
    const lazyImageCount = await page.locator(
      'img[loading="lazy"][decoding="async"][fetchpriority="low"]'
    ).count();
    const metrics = await page.evaluate(() => window.__dropfinderMetrics || {});
    const longTasks = await page.evaluate(() => window.__longTasks || []);
    const maxLongTask = longTasks.length ? Math.max(...longTasks) : 0;
    const totalLongTask = longTasks.reduce((sum, value) => sum + value, 0);
    const badNames = names.filter(name =>
      /\b\d+(?:\.\d+)?\s*(?:g|grams?|oz|ounces?)\b/i.test(name) ||
      /\bthc-?a\b/i.test(name) ||
      /[|_•·]/.test(name) ||
      /\b(?:weight|size|package|amount|quantity|option)\s*:/i.test(name)
    );

    stage = 'filter';
    const queryName = names.find(name => name && name.length >= 5) || names[0];
    const filterStarted = Date.now();
    await page.locator('#query').fill(queryName);
    await page.waitForFunction(
      expected => {
        if (document.querySelector('#grid')?.dataset.renderComplete !== 'true') return false;
        const visibleNames = [...document.querySelectorAll('.card .name')].map(node => node.textContent || '');
        return visibleNames.length >= 1 && visibleNames.every(name => name.toLowerCase().includes(expected.toLowerCase()));
      },
      queryName,
      { timeout: 3000 }
    );
    const filterMs = Date.now() - filterStarted;
    const filteredNames = await page.locator('.card .name').allInnerTexts();

    stage = 'restore_and_scroll';
    await page.locator('#query').fill('');
    await page.waitForFunction(
      expected => document.querySelector('#grid')?.dataset.renderComplete === 'true' && document.querySelectorAll('.card').length === expected,
      cardCount,
      { timeout: 5000 }
    );
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(300);
    const lastCardVisible = await page.locator('.card').last().isVisible();

    const checks = {
      all_50_products_on_one_page: cardCount === 50,
      result_count_matches: resultText.includes('50') && resultText.includes('on this page'),
      no_pagination: paginationControls === 0,
      unique_product_cards: duplicateIds.length === 0,
      all_names_canonical: badNames.length === 0,
      lazy_async_images: lazyImageCount === cardCount,
      internal_render_under_1000ms: Number(metrics.lastRenderMs || 999999) < 1000,
      max_long_task_under_500ms: maxLongTask < 500,
      total_long_task_under_2000ms: totalLongTask < 2000,
      filter_under_600ms: filterMs < 600,
      filter_correct: filteredNames.length >= 1 && filteredNames.every(name => name.toLowerCase().includes(queryName.toLowerCase())),
      last_card_reachable: lastCardVisible,
      no_page_errors: pageErrors.length === 0
    };
    const failed = Object.entries(checks).filter(([, passed]) => !passed).map(([name]) => name);
    const report = {
      schema_version: 'dropfinder-static-browser-verification-v2',
      status: failed.length ? 'failed' : 'healthy',
      verified_at: new Date().toISOString(),
      url: URL,
      viewport: { width: 390, height: 844, mobile: true },
      stage: 'complete',
      card_count: cardCount,
      result_text: resultText,
      unique_id_count: new Set(ids).size,
      duplicate_ids: [...new Set(duplicateIds)],
      bad_name_count: badNames.length,
      bad_names: badNames,
      network_and_ready_ms: readyMs,
      internal_render_ms: metrics.lastRenderMs,
      fetch_and_parse_ms: metrics.fetchAndParseMs,
      filter_query: queryName,
      filter_ms: filterMs,
      max_long_task_ms: Math.round(maxLongTask * 100) / 100,
      total_long_task_ms: Math.round(totalLongTask * 100) / 100,
      long_task_count: longTasks.length,
      image_requests_after_full_scroll: imageRequests,
      lazy_image_count: lazyImageCount,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      checks,
      failed_checks: failed,
      sample_names: names.slice(0, 30)
    };
    writeReport(report);
    console.log(JSON.stringify(report, null, 2));
    await browser.close();
    if (failed.length) process.exit(1);
  } catch (error) {
    if (browser) await browser.close();
    const report = {
      schema_version: 'dropfinder-static-browser-verification-v2',
      status: 'error',
      verified_at: new Date().toISOString(),
      url: URL,
      stage,
      error: String(error?.stack || error).slice(0, 12000),
      failed_checks: ['browser_exception']
    };
    writeReport(report);
    console.error(JSON.stringify(report, null, 2));
    process.exit(1);
  }
})();
