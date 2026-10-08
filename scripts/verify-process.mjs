/**
 * 验证「检测流程」演示区两种状态的渲染：
 *   A. 总览态：4 个块都应显示 mini（图标 + 标题 + 序号），full 全部隐藏
 *   B. 放大态：当前激活块 mini 隐藏、full 显示
 * 用法：node verify-process.mjs
 */
import { chromium } from 'playwright'

const URL = 'http://127.0.0.1:8000/app/'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

// 收集控制台报错
const errors = []
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))

await page.goto(URL, { waitUntil: 'networkidle' })

// 滚到「检测流程」区（演示区进入视口）。注意：不要在 1 秒内做判断，
// 因为自动开播会 setPicked(true)；先测【总览态】必须抢在 1 秒内。
const stage = page.locator('.process-stage')
await stage.scrollIntoViewIfNeeded()

// —— A. 总览态（DOM 层判定，比截图更硬）——
const overview = await page.evaluate(() => {
  const stage = document.querySelector('.process-stage')
  const blocks = [...document.querySelectorAll('.proc-block')]
  return {
    stageZoomed: stage?.classList.contains('is-zoomed'),
    blocks: blocks.map((b, i) => {
      const mini = b.querySelector('.proc-block-mini')
      const full = b.querySelector('.proc-block-full')
      const cs = (el) => (el ? getComputedStyle(el).opacity : null)
      return {
        i,
        active: b.classList.contains('is-active'),
        miniOpacity: cs(mini),
        fullOpacity: cs(full),
        miniText: mini?.innerText?.replace(/\s+/g, ' ').trim() || '',
        hasScene: !!full?.querySelector('.sc'),
      }
    }),
  }
})

// —— B. 放大态：等自动开播（1s）后强制点第 3 步，等动画完成 ——
await page.locator('.process-step').nth(2).click()
await page.waitForTimeout(900)

const zoomed = await page.evaluate(() => {
  const stage = document.querySelector('.process-stage')
  const blocks = [...document.querySelectorAll('.proc-block')]
  return {
    stageZoomed: stage?.classList.contains('is-zoomed'),
    blocks: blocks.map((b, i) => {
      const mini = b.querySelector('.proc-block-mini')
      const full = b.querySelector('.proc-block-full')
      const cs = (el) => (el ? getComputedStyle(el).opacity : null)
      return {
        i,
        active: b.classList.contains('is-active'),
        miniOpacity: cs(mini),
        fullOpacity: cs(full),
        fullText: full?.innerText?.replace(/\s+/g, ' ').trim() || '',
      }
    }),
  }
})

await page.screenshot({ path: '/tmp/proc-zoomed.png' })

console.log('=== A. 总览态（预期：4 块都 mini 可见、full 全 0）===')
console.log(JSON.stringify(overview, null, 2))
console.log('\n=== B. 放大态（点第3步后；预期：第3块 mini=0 / full=1，其余 mini=1 / full=0）===')
console.log(JSON.stringify(zoomed, null, 2))
console.log('\n=== 控制台错误 ===')
console.log(errors.length ? errors.join('\n') : '（无）')

// —— 自动断言 ——
const fail = []
overview.blocks.forEach((b) => {
  if (b.miniOpacity !== '1') fail.push(`总览: 块${b.i + 1} mini 不可见 (opacity=${b.miniOpacity})`)
  if (b.fullOpacity !== '0') fail.push(`总览: 块${b.i + 1} full 泄漏 (opacity=${b.fullOpacity})`)
  if (!b.miniText) fail.push(`总览: 块${b.i + 1} mini 无文字内容`)
})
const z = zoomed.blocks.find((b) => b.active)
if (!zoomed.stageZoomed) fail.push('放大态: stage 缺 is-zoomed')
if (z && z.fullOpacity !== '1') fail.push(`放大: 激活块${z.i + 1} full 不可见 (opacity=${z.fullOpacity})`)
if (z && z.miniOpacity !== '0') fail.push(`放大: 激活块${z.i + 1} mini 未隐藏 (opacity=${z.miniOpacity})`)
zoomed.blocks.filter((b) => !b.active).forEach((b) => {
  if (b.fullOpacity !== '0') fail.push(`放大: 非激活块${b.i + 1} full 泄漏 (opacity=${b.fullOpacity})`)
})

console.log('\n=== 结论 ===')
console.log(fail.length ? '✘ FAIL\n' + fail.join('\n') : '✔ PASS —— 两个状态的显隐逻辑全部正确')

await browser.close()
process.exit(fail.length ? 1 : 0)
