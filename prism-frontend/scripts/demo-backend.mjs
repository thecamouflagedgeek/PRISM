import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, appendFileSync } from 'node:fs';
import { resolve } from 'node:path';

mkdirSync('.demo-runtime', { recursive: true });
writeFileSync('.demo-runtime/backend.log', '');
const child = spawn(resolve('../backend/.venv/Scripts/python.exe'), ['-u', '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', process.env.PRISM_DEMO_PORT || '8000'], {
  cwd: resolve('../backend'), env: { ...process.env, PRISM_ENV: 'demo', PRISM_DEMO_FIXTURES: 'true',
    ENABLE_EXPERIMENTAL_SHADOW_SCORING: 'true', PRISM_LENDER_PHONES: '+19990000002' },
});
for (const pipe of [child.stdout, child.stderr]) pipe.on('data', data => { appendFileSync('.demo-runtime/backend.log', data); process.stdout.write(data); });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill());
child.on('exit', code => process.exit(code || 0));
