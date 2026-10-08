import { chromium } from 'playwright'
const BASE = 'http://127.0.0.1:8000/app'
const EXPECT = [
  { i: 0, label: '模型状态', clickable: true, dest: '/detect',      authGated: false },
  { i: 1, label: '医疗问答', clickable: true, dest: '/chat',        authGated: true  },
  { i: 2, label: '识别精度', clickable: false, dest: null,          authGated: false },
  { i: 3, label: '我的检测', clickable: true, dest: '/history',     authGated: true  },
]
const browser = await chromium.launch()
const fails = []
const report = []

async function readCells(page) {
  return page.evaluate(() => {
    const grid = [...document.querySelectorAll('.hero-fade-fast')]
      .find((el) => /模型状态/.test(el.textContent))
    return [...grid.children].map((c) => ({
      tag: c.tagName.toLowerCase(),
      href: c.getAttribute('href') || '',
      text: c.innerText.replace(/\s+/g, ' ').trim(),
      cls: c.classList.contains('stat-card-clickable'),
      cursor: getComputedStyle(c).cursor,
      opacity: getComputedStyle(c).opacity,
      pointerEvents: getComputedStyle(c).pointerEvents,
    }))
  })
}

for (const e of EXPECT) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const errs = []
  page.on('pageerror', (x) => errs.push(x.message))
  await page.goto(BASE + '/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(600)

  const cells = await readCells(page)
  const c = cells[e.i]
  const line = { label: e.label, ...c }
  console.log(`\n--- 第${e.i + 1}格「${e.label}」---`)
  console.log('  ' + JSON.stringify(c))
  report.push(line)

  if (e.clickable) {
    if (c.tag !== 'a') fails.push(`${e.label}: 应为 <a>，实际 <${c.tag}>`)
    if (!c.href.endsWith(e.dest)) fails.push(`${e.label}: href=${c.href} 不含 ${e.dest}`)
    if (!c.cls) fails.push(`${e.label}: 缺 stat-card-clickable`)
    if (c.cursor !== 'pointer') fails.push(`${e.label}: cursor=${c.cursor} 期望 pointer`)

    // 真点：用 DOM 直接触发 click，避免淡出层/滚动位置干扰
    await page.evaluate((idx) => {
      const grid = [...document.querySelectorAll('.hero-fade-fast')]
        .find((el) => /模型状态/.test(el.textContent))
      grid.children[idx].click()
    }, e.i)
    await page.waitForTimeout(800)
    const path = new URL(page.url()).pathname.replace(/^\/app/, '')
    console.log(`  点击后 → ${path}`)
    if (e.authGated) {
      if (path !== '/login') fails.push(`${e.label}: 未登录应跳 /login，实际 ${path}`)
      else console.log('  ✔ 未登录 → 正确被 RequireAuth 送到 /login')
    } else if (path !== e.dest) {
      fails.push(`${e.label}: 期望 ${e.dest}，实际 ${path}`)
    } else console.log(`  ✔ 正确跳转到 ${e.dest}`)
  } else {
    if (c.tag === 'a') fails.push(`${e.label}: 不应可点击，却是 <a href="${c.href}">`)
    const before = page.url()
    await page.evaluate((idx) => {
      const grid = [...document.querySelectorAll('.hero-fade-fast')]
        .find((el) => /模型状态/.test(el.textContent))
      grid.children[idx].click()
    }, e.i)
    await page.waitForTimeout(500)
    if (page.url() !== before) fails.push(`${e.label}: 不应跳转，却跳到了 ${page.url()}`)
    else console.log('  ✔ 点击无跳转')
  }
  if (errs.length) fails.push(`${e.label}: 控制台报错 ${errs.join(' | ')}`)
  await ctx.close()
}

console.log('\n=== 结论 ===')
console.log(fails.length ? '✘ FAIL\n' + fails.map((f) => ' - ' + f).join('\n') : '✔ PASS —— 四格跳转行为全部符合预期')
await browser.close()
process.exit(fails.length ? 1 : 0)
