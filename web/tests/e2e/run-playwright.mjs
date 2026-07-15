import { spawnSync } from 'node:child_process';

const result = spawnSync(process.platform === 'win32' ? 'npx.cmd' : 'npx', ['playwright', 'test'], { stdio: 'inherit' });
process.exitCode = result.status ?? 1;
