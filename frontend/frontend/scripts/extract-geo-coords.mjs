import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const src = fs.readFileSync(path.join(root, '门店销售智能看板/js/mymap.js'), 'utf8')
const geoBlock = src.slice(src.indexOf('var geoCoordMap = '), src.indexOf('var BJData'))
const geo = Function(`return ${geoBlock.replace('var geoCoordMap = ', '')}`)()
const used = new Set()
for (const block of ['BJData', 'SHData', 'GZData']) {
  const i = src.indexOf(`var ${block}`)
  const j = src.indexOf('var ', i + 10)
  const part = src.slice(i, j > 0 ? j : undefined)
  const names = [...part.matchAll(/name:\s*'([^']*)'/g)].map((m) => m[1])
  names.forEach((n) => used.add(n))
}
const picked = {}
for (const n of used) {
  if (geo[n]) picked[n] = geo[n]
}
const out = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  '../src/components/store-sales-dashboard/geoCoordMap.json',
)
fs.mkdirSync(path.dirname(out), { recursive: true })
fs.writeFileSync(out, JSON.stringify(picked, null, 2))
console.log('cities', Object.keys(picked).length)
