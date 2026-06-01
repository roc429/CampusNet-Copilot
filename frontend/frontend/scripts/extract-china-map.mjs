import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const src = path.join(root, '门店销售智能看板/js/china.js')
const out = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  '../public/store-sales-dashboard/china-map.json',
)

const s = fs.readFileSync(src, 'utf8')
const marker = "registerMap('china', "
const i = s.indexOf(marker)
if (i < 0) throw new Error('registerMap not found')
const start = i + marker.length
const endMarker = 'UTF8Encoding":true}'
const endIdx = s.indexOf(endMarker, start)
if (endIdx < 0) throw new Error('geo json end marker not found')
const json = s.slice(start, endIdx + endMarker.length)
JSON.parse(json)
fs.mkdirSync(path.dirname(out), { recursive: true })
fs.writeFileSync(out, json)
console.log('wrote', out, json.length, 'bytes')
