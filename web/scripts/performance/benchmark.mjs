import { performance } from 'node:perf_hooks';
import { executeQuery } from '../../src/platform/workers/marketplace-query-engine.js';
import { VirtualMarketplaceAdapter } from '../../src/platform/virtualization/virtual-marketplace-adapter.js';

const sizes = [1_000, 10_000, 50_000];
const budgets = { 1_000: 100, 10_000: 100, 50_000: 250 };

function fixture(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: `p-${String(index).padStart(6, '0')}`,
    vendorId: `vendor-${index % 37}`,
    vendor: `Vendor ${index % 37}`,
    strain: `Strain ${index % 997}`,
    lineage: ['indica', 'indica_hybrid', 'hybrid', 'sativa_hybrid', 'sativa', 'unknown'][index % 6],
    totalThc: 10 + (index % 30) + ((index % 10) / 10),
    image: index % 4 ? `https://fixtures.invalid/${index}.webp` : null,
    detailShard: index % 3 ? `details/${index % 100}.json` : null,
    variants: [3.5, 7, 14, 28].map((weight, variantIndex) => ({
      id: `p-${index}-v-${variantIndex}`,
      weight,
      price: Number((weight * (3 + ((index + variantIndex) % 10) / 3)).toFixed(2)),
      ppg: Number((3 + ((index + variantIndex) % 10) / 3).toFixed(4)),
    })),
  }));
}

const request = {
  search: 'strain 2', vendors: [], lineages: ['hybrid', 'sativa'],
  minTotalThc: 15, maxTotalThc: 38, minWeight: 7, maxWeight: 28,
  minPrice: 20, maxPrice: 180, minPpg: 3, maxPpg: 8,
  sort: 'lowest_ppg', offset: 0, limit: 120, expandedProductId: null,
};

const results = [];
for (const size of sizes) {
  const rows = fixture(size);
  for (let warmup = 0; warmup < 3; warmup += 1) executeQuery(rows, request);
  const samples = [];
  for (let iteration = 0; iteration < 7; iteration += 1) {
    const start = performance.now();
    executeQuery(rows, request);
    samples.push(performance.now() - start);
  }
  samples.sort((a, b) => a - b);
  const p50 = samples[Math.floor(samples.length * 0.5)];
  const p95 = samples[Math.floor(samples.length * 0.95)];
  const adapter = new VirtualMarketplaceAdapter({ estimatedRowHeight: 176, overscanPx: 420 });
  adapter.replace({ rows: rows.slice(0, Math.min(rows.length, 1_000)).map(row => ({ productId: row.id })), total: size, version: 1 });
  adapter.setViewport(20_000, 900);
  const renderedRows = adapter.window().renderedCount;
  const budget = budgets[size];
  const passed = p95 <= budget && renderedRows <= 20;
  results.push({ size, p50: Number(p50.toFixed(2)), p95: Number(p95.toFixed(2)), budget, renderedRows, passed });
}

console.table(results);
console.log(JSON.stringify({
  environment: { node: process.version, platform: process.platform, arch: process.arch, cpuCount: (await import('node:os')).cpus().length },
  results,
}, null, 2));
if (results.some(result => !result.passed)) process.exitCode = 1;
