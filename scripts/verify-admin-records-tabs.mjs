/**
 * 后台「检测记录」页验证：
 *   1. 顶部有「图像检测 / 问答记录」切换按钮，角标数字正确
 *   2. 切到问答记录：表格渲染出会话（标题/用户/消息数/首问/时间）
 *   3. 问答详情弹窗：以气泡还原对话，AI 回答带模型名与耗时
 *   4. URL 参数 ?tab=chat 能直接打开问答视图（看板问答列跳转）
 *   5. URL 参数 ?tab=chat&username=admin 能过滤
 *   6. 切回图像检测：原表格仍正常
 * 用法：node verify-admin-records-tabs.mjs
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

// 登录并写入后台所需的 localStorage（⚠️ admin.js: skin_token + skin_admin_user，且 role 必须为 admin）
const d = await fetch(BASE + '/api/auth/login', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: '<密码>' }),
}).then((r) => r.json())

await page.goto(BASE + '/admin/records.html', { waitUntil: 'domcontentloaded' })
await page.evaluate(({ t, u }) => {
  localStorage.setItem('skin_token', t)
  localStorage.setItem('skin_admin_user', JSON.stringify(u))
}, { t: d.token, u: d.user })

// ---------- 1. 默认视图（图像检测）+ 角标 ----------
await page.goto(BASE + '/admin/records.html', { waitUntil: 'networkidle' })
await page.waitForTimeout(2200)
console.log('\n=== 1. 默认视图与角标 ===')
const t1 = await page.evaluate(() => ({
  url: location.search || '(无参数)',
  recordVisible: !document.getElementById('view-record').classList.contains('d-none'),
  chatHidden: document.getElementById('view-chat').classList.contains('d-none'),
  tabRecordActive: document.getElementById('tab-record').classList.contains('active'),
  badgeRecord: document.getElementById('badgeRecord').textContent,
  badgeChat: document.getElementById('badgeChat').textContent,
  recordRows: document.querySelectorAll('#tbody tr').length,
}))
console.log(' ', JSON.stringify(t1))
if (!t1.recordVisible || !t1.chatHidden) fails.push('默认应显示图像检测视图')
if (!t1.tabRecordActive) fails.push('默认「图像检测」tab 未高亮')
if (t1.badgeRecord !== '1442 条') fails.push(`图像角标应为 "1442 条"，实际 "${t1.badgeRecord}"`)
if (t1.badgeChat !== '7 个') fails.push(`问答角标应为 "7 个"，实际 "${t1.badgeChat}"`)
if (t1.recordRows < 1) fails.push('图像检测表格无数据行')

// ---------- 2. 点击切到问答记录 ----------
await page.click('#tab-chat')
await page.waitForTimeout(1800)
console.log('\n=== 2. 切到问答记录 ===')
const t2 = await page.evaluate(() => ({
  url: location.search,
  chatVisible: !document.getElementById('view-chat').classList.contains('d-none'),
  recordHidden: document.getElementById('view-record').classList.contains('d-none'),
  tabChatActive: document.getElementById('tab-chat').classList.contains('active'),
  badge: document.getElementById('chatTotalBadge').textContent,
  headers: [...document.querySelectorAll('#view-chat thead th')].map((x) => x.textContent.trim()),
  rows: [...document.querySelectorAll('#chatBody tr')].slice(0, 3).map((tr) =>
    [...tr.children].map((td) => td.textContent.trim().replace(/\s+/g, ' ').slice(0, 22))),
  rowCount: document.querySelectorAll('#chatBody tr').length,
  pageInfo: document.getElementById('chatPageInfo').textContent,
}))
console.log('  URL 参数:', t2.url)
console.log('  表头:', JSON.stringify(t2.headers))
t2.rows.forEach((r) => console.log('  ', JSON.stringify(r)))
console.log('  底栏:', t2.pageInfo)
if (!t2.chatVisible || !t2.recordHidden) fails.push('切到问答后视图未正确显隐')
if (!t2.tabChatActive) fails.push('问答 tab 未高亮')
if (t2.url !== '?tab=chat') fails.push(`URL 应带 ?tab=chat，实际 "${t2.url}"`)
if (t2.rowCount < 1) fails.push('问答列表无数据行')
if (!t2.headers.includes('消息数')) fails.push('问答表头缺「消息数」')
if (!t2.pageInfo.includes('共 7 条')) fails.push(`问答分页信息异常: ${t2.pageInfo}`)

// ---------- 3. 打开问答详情（气泡） ----------
await page.click('#chatBody tr:first-child a')
await page.waitForTimeout(2000)
console.log('\n=== 3. 问答详情弹窗（气泡） ===')
const t3 = await page.evaluate(() => {
  const modal = document.getElementById('chatModal')
  return {
    shown: modal.classList.contains('show'),
    title: document.getElementById('chatModalId').textContent,
    bubbles: [...document.querySelectorAll('#chatBodyModal .bubble')].map((b) =>
      b.textContent.trim().replace(/\s+/g, ' ').slice(0, 34)),
    meCount: document.querySelectorAll('#chatBodyModal .bubble-row.me').length,
    aiCount: document.querySelectorAll('#chatBodyModal .bubble-row.ai').length,
    metas: [...document.querySelectorAll('#chatBodyModal .bubble-meta')].map((m) => m.textContent.trim()).slice(0, 4),
    hasDisclaimer: !!document.querySelector('#chatBodyModal .alert-warning'),
  }
})
console.log('  弹窗:', t3.title, '| shown =', t3.shown)
console.log('  气泡数: 用户', t3.meCount, '/ AI', t3.aiCount, '| 免责声明:', t3.hasDisclaimer)
t3.bubbles.slice(0, 4).forEach((b, i) => console.log(`   [${i}] ${b}`))
console.log('  元信息:', JSON.stringify(t3.metas))
if (!t3.shown) fails.push('问答详情弹窗未打开')
if (t3.meCount < 1 || t3.aiCount < 1) fails.push('气泡未区分用户/AI')
if (!t3.hasDisclaimer) fails.push('详情缺免责声明')
await page.click('#chatModal .btn-secondary')
await page.waitForTimeout(600)

// ---------- 4. URL ?tab=chat 直接进问答视图 ----------
await page.goto(BASE + '/admin/records.html?tab=chat', { waitUntil: 'networkidle' })
await page.waitForTimeout(2000)
console.log('\n=== 4. 直达 ?tab=chat ===')
const t4 = await page.evaluate(() => ({
  chatVisible: !document.getElementById('view-chat').classList.contains('d-none'),
  tabChatActive: document.getElementById('tab-chat').classList.contains('active'),
  rows: document.querySelectorAll('#chatBody tr').length,
}))
console.log(' ', JSON.stringify(t4))
if (!t4.chatVisible || !t4.tabChatActive) fails.push('?tab=chat 未直接打开问答视图')

// ---------- 5. ?tab=chat&username=admin 过滤 ----------
await page.goto(BASE + '/admin/records.html?tab=chat&username=admin', { waitUntil: 'networkidle' })
await page.waitForTimeout(2000)
console.log('\n=== 5. ?tab=chat&username=admin 过滤 ===')
const t5 = await page.evaluate(() => ({
  inputVal: document.getElementById('c-username').value,
  users: [...new Set([...document.querySelectorAll('#chatBody tr')].map((tr) =>
    tr.children[2]?.textContent.trim()))],
  count: document.querySelectorAll('#chatBody tr').length,
  pageInfo: document.getElementById('chatPageInfo').textContent,
}))
console.log(' ', JSON.stringify(t5))
if (t5.inputVal !== 'admin') fails.push('username 参数未回填到筛选框')
if (t5.users.length && t5.users.some((u) => u && u !== 'admin')) fails.push(`过滤失效，出现其他用户: ${t5.users}`)

// ---------- 6. 切回图像检测 ----------
await page.goto(BASE + '/admin/records.html', { waitUntil: 'networkidle' })
await page.waitForTimeout(2000)
await page.click('#tab-chat'); await page.waitForTimeout(1500)
await page.click('#tab-record'); await page.waitForTimeout(1800)
console.log('\n=== 6. 问答→图像 切回 ===')
const t6 = await page.evaluate(() => ({
  recordVisible: !document.getElementById('view-record').classList.contains('d-none'),
  rows: document.querySelectorAll('#tbody tr').length,
  url: location.search || '(无)',
  badge: document.getElementById('totalBadge').textContent,
}))
console.log(' ', JSON.stringify(t6))
if (!t6.recordVisible || t6.rows < 1) fails.push('切回图像检测后表格异常')
if (t6.url !== '(无)') fails.push(`切回后 URL 应无参数，实际 "${t6.url}"`)

await page.screenshot({ path: '/tmp/admin-records-chat.png', fullPage: false })

console.log('\n=== 控制台错误 ===')
console.log(errs.length ? errs.join('\n') : '（无）')
if (errs.length) fails.push('存在控制台报错')

console.log('\n=== 结论 ===')
console.log(fails.length ? '✘ FAIL\n' + fails.map((f) => ' - ' + f).join('\n') : '✔ PASS —— 记录页切换与问答视图全部正常')
await browser.close()
process.exit(fails.length ? 1 : 0)
