/**
 * Strip title text from store-sales-dashboard logo.png while preserving frame art.
 * Source: logo-original.png (BigDataView template)
 */
import { Jimp } from 'jimp'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const publicDir = path.join(__dirname, '../public/store-sales-dashboard/images')
const srcPath = path.join(publicDir, 'logo-original.png')
const outPath = path.join(publicDir, 'logo.png')

/** Diamond icon in center header */
function preserveDiamond(x, y) {
  return x >= 938 && x <= 952 && y >= 40 && y <= 70
}

/** [x0, x1, y0, y1] inclusive */
const TEXT_BOXES = [
  [838, 932, 34, 75], // 立可得 + fastest
  [943, 1098, 36, 73], // 智能看板 (+ antialiasing halo)
  [672, 1232, 84, 92], // English subtitle line
]

function alpha(pixel) {
  return pixel & 255
}

function inBox(x, y, box) {
  const [x0, x1, y0, y1] = box
  return x >= x0 && x <= x1 && y >= y0 && y <= y1
}

function stripText(im) {
  const w = im.bitmap.width
  const h = im.bitmap.height
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (preserveDiamond(x, y)) continue
      let inText = false
      for (const box of TEXT_BOXES) {
        if (inBox(x, y, box)) {
          inText = true
          break
        }
      }
      if (!inText) continue
      if (alpha(im.getPixelColor(x, y)) > 3) {
        im.setPixelColor(0x00000000, x, y)
      }
    }
  }
}

const im = await Jimp.read(srcPath)
stripText(im)
await im.write(outPath)
console.log('Wrote', outPath)
