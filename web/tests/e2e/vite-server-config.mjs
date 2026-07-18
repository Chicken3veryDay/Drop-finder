import { isIP } from 'node:net';

export const E2E_VITE_HOST = '127.0.0.1';
export const E2E_VITE_PORT = '4173';

export function isLoopbackHost(host) {
  const normalized = String(host).trim().toLowerCase();
  if (normalized === 'localhost' || normalized === '::1') return true;
  if (isIP(normalized) !== 4) return false;
  return normalized.split('.')[0] === '127';
}

export function createViteArguments() {
  if (!isLoopbackHost(E2E_VITE_HOST)) {
    throw new Error(`Managed E2E Vite host must be loopback-only: ${E2E_VITE_HOST}`);
  }

  return [
    'vite',
    '--host',
    E2E_VITE_HOST,
    '--port',
    E2E_VITE_PORT,
    '--strictPort',
    '--force',
  ];
}
