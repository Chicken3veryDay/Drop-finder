import { spawn } from 'node:child_process';

const executable = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const child = spawn(
  executable,
  ['vite', '--host', '0.0.0.0', '--port', '4173', '--strictPort', '--force'],
  {
    stdio: 'inherit',
    env: { ...process.env, DROPFINDER_E2E: '1' },
  },
);

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => {
    if (!child.killed) child.kill(signal);
  });
}

child.once('error', error => {
  console.error(error);
  process.exitCode = 1;
});

child.once('exit', (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});
