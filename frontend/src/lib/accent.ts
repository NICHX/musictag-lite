/** 封面取色：从封面提取主色，用于 --accent-dynamic（设计文档 §10.6）。 */

export interface Hsl {
  h: number
  s: number
  l: number
}

/** RGB(0-255) → HSL(h:0-360, s:0-1, l:0-1)。纯函数，便于测试。 */
export function rgbToHsl(r: number, g: number, b: number): Hsl {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const l = (max + min) / 2
  const delta = max - min

  if (delta === 0) return { h: 0, s: 0, l }

  const s = l > 0.5 ? delta / (2 - max - min) : delta / (max + min)
  let h: number
  if (max === rn) h = ((gn - bn) / delta) % 6
  else if (max === gn) h = (bn - rn) / delta + 2
  else h = (rn - gn) / delta + 4

  h *= 60
  if (h < 0) h += 360
  return { h, s, l }
}

/** 把平均色提升为可用作强调色的鲜艳色（固定饱和与亮度区间）。 */
export function vividAccent(r: number, g: number, b: number): string {
  const { h, s } = rgbToHsl(r, g, b)
  const saturation = Math.min(0.85, Math.max(0.45, s))
  const lightness = 0.58
  return `hsl(${Math.round(h)} ${Math.round(saturation * 100)}% ${Math.round(lightness * 100)}%)`
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('图片加载失败'))
    image.src = url
  })
}

/** 从封面 URL 提取强调色；失败（含跨域污染）时返回 null。 */
export async function extractAccent(url: string, sample = 24): Promise<string | null> {
  try {
    const image = await loadImage(url)
    const canvas = document.createElement('canvas')
    canvas.width = sample
    canvas.height = sample
    const context = canvas.getContext('2d')
    if (!context) return null
    context.drawImage(image, 0, 0, sample, sample)
    const { data } = context.getImageData(0, 0, sample, sample)

    let r = 0
    let g = 0
    let b = 0
    let count = 0
    for (let i = 0; i < data.length; i += 4) {
      r += data[i]
      g += data[i + 1]
      b += data[i + 2]
      count += 1
    }
    if (!count) return null
    return vividAccent(r / count, g / count, b / count)
  } catch {
    return null
  }
}
