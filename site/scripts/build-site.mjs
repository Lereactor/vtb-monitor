// Build the live site for GitHub Pages and, with --deploy, publish it.
//
//   node scripts/build-site.mjs            — build into dist-site/
//   node scripts/build-site.mjs --deploy   — build and force-push to main of Lereactor/vtb-monitor-live
//
// No secrets here: the data (and the encrypted private part) are pushed by the VPS to the
// repo's `data` branch and read by the browser from raw.githubusercontent.com.
import { execSync } from 'node:child_process'
import { rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO = 'Lereactor/vtb-monitor-live'
const BASE = '/vtb-monitor-live/'

const site = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(site, 'dist-site')

rmSync(out, { recursive: true, force: true })
execSync(`npx tsc -b && npx vite build --base ${BASE} --outDir dist-site --emptyOutDir`, { cwd: site, stdio: 'inherit' })
writeFileSync(join(out, '.nojekyll'), '')

if (process.argv.includes('--deploy')) {
  const run = (cmd) => execSync(cmd, { cwd: out, stdio: 'inherit' })
  run('git init -q -b main')
  run('git add -A')
  run('git -c user.name=vtb-monitor -c user.email=vtb-monitor@localhost commit -q -m "site"')
  run(`git push -q -f https://github.com/${REPO}.git main`)
  console.log(`Выложено: https://${REPO.split('/')[0].toLowerCase()}.github.io${BASE}`)
}
