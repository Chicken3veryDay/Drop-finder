import assert from 'node:assert/strict';
import test from 'node:test';

import {
  E2E_VITE_HOST,
  createViteArguments,
  isLoopbackHost,
} from '../tests/e2e/vite-server-config.mjs';

test('managed E2E Vite server is restricted to loopback', () => {
  const args = createViteArguments();
  const hostFlag = args.indexOf('--host');

  assert.notEqual(hostFlag, -1);
  assert.equal(args[hostFlag + 1], E2E_VITE_HOST);
  assert.equal(isLoopbackHost(E2E_VITE_HOST), true);
  assert.equal(isLoopbackHost('0.0.0.0'), false);
  assert.equal(isLoopbackHost('::'), false);
  assert.equal(isLoopbackHost('192.168.1.10'), false);
});

test('loopback validation accepts supported local host forms', () => {
  assert.equal(isLoopbackHost('127.0.0.1'), true);
  assert.equal(isLoopbackHost('127.10.20.30'), true);
  assert.equal(isLoopbackHost('localhost'), true);
  assert.equal(isLoopbackHost('::1'), true);
});
