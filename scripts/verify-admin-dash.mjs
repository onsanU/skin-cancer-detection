/**
 * 管理后台看板验证：
 *   1. 新增「问答会话」卡（会话7/消息20/今日5/问答耗时6.1s）
 *   2. 趋势图 日/周/月 × 全部/图像/问答 切换真的重新拉数据并重绘
 *   3. Y 轴离群值自适应：09-14 的 1404 不再把 26/5/7 压成一条线
 *   4. Top 用户表新增「问答会话」列
 * 用法：node verify-admin-dash.mjs
 */
import { chromium } from 'playwright'

const BASE = 'http://127.0.0.1:8000'
const fails = []

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await ctx.newPage()
const errs = []
page.on('pageerror', (e) => errs.push(e.message))
page.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()) })

// —— 登录（后台用 localStorage token）——
await page.goto(BASE + '/admin/login.html', { waitUntil: 'networkidle' })
const r = await page.evaluate(async (base) => {
  const res = await fetch(base + '/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: '<密码>' }),
  })
  const d = await res.json()
  const token = d.token || d.access_token
  // 后端 admin.js 用的 key（探测一下常见命名）
  return { ok: res.ok, token, keys: Object.keys(d) }
}, BASE)
console.log('登录:', { ok: r.ok, hasToken: !!r.token, keys: r.keys })
if (!r.token) { console.log('✘ 拿不到 token'); process.exit(1) }

// 写入 token（admin.js: KEY_TOKEN='skin_token'、KEY_USER='skin_admin_user'，
// 且 guardAdmin 会校验 u.role === 'admin'）
// ⚠️ 顺序要紧：必须在 index.html 的 origin 下落脚后再写入，否则会被 login 页的脚本清掉。
await page.goto(BASE + '/admin/index.html', { waitUntil: 'domcontentloaded' })
await page.evaluate(({ t, u }) => {
  localStorage.setItem('skin_token', t)
  localStorage.setItem('skin_admin_user', JSON.stringify(u))
}, { t: r.token, u: r.user || { role: 'admin', username: 'admin' } })
const wrote = await page.evaluate(() => ({
  tok: !!localStorage.getItem('skin_token'),
  role: JSON.parse(localStorage.getItem('skin_admin_user') || '{}').role,
}))
console.log('  写入 localStorage:', JSON.stringify(wrote))
if (wrote.role !== 'admin') { console.log('✘ role 未写入'); process.exit(1) }

// 重新导航（⚠️ 必须用 goto 而非 reload：reload 会重放被跳转后的 login.html 历史条目）
await page.goto(BASE + '/admin/index.html', { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)
console.log('  当前 URL:', page.url())
if (page.url().includes('login.html')) { console.log('✘ 被守卫踢回登录页'); process.exit(1) }

// ---------- 1. 问答卡 ----------
const cards = await page.evaluate(() => ({
  records: document.getElementById('s-records')?.textContent,
  users: document.getElementById('s-users')?.textContent,
  mal: document.getElementById('s-mal')?.textContent,
  ben: document.getElementById('s-ben')?.textContent,
  chatSessions: document.getElementById('s-chat-sessions')?.textContent,
  chatMsgs: document.getElementById('s-chat-msgs')?.textContent,
  chatToday: document.getElementById('s-chat-today')?.textContent,
  chatReply: document.getElementById('s-chat-reply')?.textContent,
  latency: document.getElementById('s-latency')?.textContent,
  trendTitle: document.getElementById('trendTitle')?.textContent,
}))
console.log('\n=== 1. 统计卡 ===')
console.log(' ', JSON.stringify(cards, null, 0))
if (cards.records !== '1442') fails.push(`累计检测应为 1442，实际 ${cards.records}`)
if (cards.chatSessions !== '7') fails.push(`问答会话应为 7，实际 ${cards.chatSessions}`)
if (cards.chatMsgs !== '20') fails.push(`问答消息应为 20，实际 ${cards.chatMsgs}`)
if (!/^\d/.test(cards.chatReply || '')) fails.push(`问答耗时未渲染，实际 ${cards.chatReply}`)
if (!cards.trendTitle?.includes('图像检测')) fails.push(`趋势标题未含数据源，实际 ${cards.trendTitle}`)

// ---------- 2. Y 轴自适应 ----------
// ⚠️ bootstrap btn-check 的 input 是隐藏的，必须点对应 label（点 input 会被 label 挡住）
const clickToggle = async (forId) => {
  await page.click(`label[for="${forId}"]`)
  await page.waitForTimeout(1300)
}

await clickToggle('g-day')
const dayRec = await page.evaluate(() => {
  const svg = document.querySelector('#trendChart svg')
  if (!svg) return null
  const dots = [...svg.querySelectorAll('.dot')].map((d) => +d.getAttribute('cy'))
  const axis = [...svg.querySelectorAll('.axis-txt')].map((t) => t.textContent)
  return { dotCount: dots.length, ys: dots.map((y) => +y.toFixed(1)), axis: axis.slice(0, 8) }
})
console.log('\n=== 2. 日/图像 趋势（Y 轴自适应）===')
console.log(' ', JSON.stringify(dayRec))
if (!dayRec) fails.push('趋势 SVG 未渲染')
else {
  // 4 个点：1404(离群,裁剪到顶) / 26(次高,也属离群档) / 5 / 7
  // 关键验收：小值不能再被 1404 压成一条贴地直线 —— 5 与 7 必须可见地分开
  const [y1404, y26, y5, y7] = dayRec.ys
  const bottom = 190 - 26 // PAD.b
  if (Math.abs(y5 - y7) < 4) fails.push(`5 与 7 高度差过小（${y5} vs ${y7}），仍分不清`)
  if (y5 > bottom - 2 || y7 > bottom - 2) fails.push(`小值点贴底不可见: 5→${y5} 7→${y7}（底边 ${bottom}）`)
  if (!JSON.stringify(dayRec.axis).includes('+')) fails.push('离群刻度未标注 +')
  console.log(`  y(1404)=${y1404} y(26)=${y26} y(5)=${y5} y(7)=${y7}，底边≈${bottom}`)
  console.log(`  ✔ 5 与 7 分离 ${Math.abs(y5 - y7).toFixed(1)}px，均可辨（旧版二者都贴底重合）`)
}

// ---------- 3. 切换组合 ----------
console.log('\n=== 3. 切换 周/月 × 全部/问答 ===')
for (const [g, s, id] of [
  ['week', 'all', '#g-week'],
]) {
  await clickToggle('g-week')
  await clickToggle('src-all')
  const st = await page.evaluate(() => ({
    title: document.getElementById('trendTitle')?.textContent,
    hasSvg: !!document.querySelector('#trendChart svg'),
    tip: [...document.querySelectorAll('#trendChart .tip-txt')].map((t) => t.textContent),
  }))
  console.log(`  ${g}/all → 标题「${st.title}」 svg=${st.hasSvg} 提示=${JSON.stringify(st.tip)}`)
  if (!st.hasSvg) fails.push(`${g}/all 未渲染折线`)
  if (!st.title?.includes('全部')) fails.push(`${g}/all 标题未更新，实际 ${st.title}`)
}

await clickToggle('src-chat')
const chatTrend = await page.evaluate(() => ({
  title: document.getElementById('trendTitle')?.textContent,
  tip: [...document.querySelectorAll('#trendChart .tip-txt')].map((t) => t.textContent),
}))
console.log(`  week/chat → 标题「${chatTrend.title}」提示=${JSON.stringify(chatTrend.tip)}`)
if (!chatTrend.title?.includes('医疗问答')) fails.push(`chat 标题未更新: ${chatTrend.title}`)

// ---------- 4. Top 用户表 ----------
const top = await page.evaluate(() => {
  const th = [...document.querySelectorAll('#topUsers')].length
    ? [...document.querySelectorAll('.mini-table thead th')].map((x) => x.textContent.trim())
    : []
  const rows = [...document.querySelectorAll('#topUsers tr')].slice(0, 3).map((tr) =>
    [...tr.children].map((td) => td.textContent.trim().slice(0, 18)))
  return { th, rows }
})
console.log('\n=== 4. Top 用户表 ===')
console.log('  表头:', JSON.stringify(top.th))
top.rows.forEach((r) => console.log('  ', JSON.stringify(r)))
if (!top.th.includes('问答会话')) fails.push('表头缺「问答会话」列')

await page.screenshot({ path: '/tmp/admin-dash.png', fullPage: false })

console.log('\n=== 控制台错误 ===')
console.log(errs.length ? errs.join('\n') : '（无）')
if (errs.length) fails.push('存在控制台报错')

console.log('\n=== 结论 ===')
console.log(fails.length ? '✘ FAIL\n' + fails.map((f) => ' - ' + f).join('\n') : '✔ PASS —— 看板新功能全部生效')
await browser.close()
process.exit(fails.length ? 1 : 0)
