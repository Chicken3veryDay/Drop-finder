import { executeQuery } from './marketplace-query-engine.js';

let generationId = null;
let rows = [];
let latestVersion = 0;

self.onmessage = event => {
  const message = event.data;
  if (message?.type === 'initialize') {
    generationId = message.generationId;
    rows = message.rows;
    latestVersion = 0;
    return;
  }
  if (message?.type !== 'query' || message.generationId !== generationId) return;
  latestVersion = Math.max(latestVersion, message.version);
  const version = message.version;
  const result = executeQuery(rows, message.request, version, generationId);
  if (version !== latestVersion) return;
  self.postMessage({ type: 'result', generationId, version, result });
};
