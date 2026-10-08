/**
 * 后台「系统状态」页验证：
 *   1. 页面能加载（不再 500），无 JS 报错
 *   2. 服务信息 / 模型状态 / 推理配置 / 数据库 / 存储 各区块有值
 *   3. 集成成员显示为「目录/文件」而不是 [object Object]
 * 用法：node verify-admin-system.mjs
 */
import { chromium } from 'playwright'

const BASE = 'http://127.0.0.1:8000'
const fails = []

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } })
const page = await ctx.newPage()
const errs = []
page.on('pageerror', (e) => errs.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()) })
// 记录接口响应状态
const apiStatus = {}
page.on('response', (r) => {
  const u = new URL(r.url()).pathname
  if (u.startsWith('/admin/api')) apiStatus[u] = r.status()
})

const d = await fetch(BASE + '/api/auth/login', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: '<密码>' }),
}).then((r) => r.json())

await page.goto(BASE + '/admin/system.html', { waitUntil: 'domcontentloaded' })
await page.evaluate(({ t, u }) => {
  localStorage.setItem('skin_token', t)
  localStorage.setItem('skin_admin_user', JSON.stringify(u))
}, { t: d.token, u: d.user })
await page.goto(BASE + '/admin/system.html', { waitUntil: 'networkidle' })
await page.waitForTimeout(3000)

console.log('=== 0. 接口状态码 ===')
console.log(' ', JSON.stringify(apiStatus))
for (const [u, s] of Object.entries(apiStatus)) {
  if (s >= 400) fails.push(`${u} 返回 HTTP ${s}`)
}

console.log('\n=== 1. 页面结构 ===')
const layout = await page.evaluate(() => ({
  url: location.pathname,
  bodyLen: document.body.innerText.length,
  hasErrorAlert: !!document.querySelector('.alert-danger'),
  errorText: document.querySelector('.alert-danger')?.innerText?.slice(0, 120) || '',
  tables: [...document.querySelectorAll('table')].map((t) => t.id || '(无id)'),
}))
console.log(' ', JSON.stringify(layout))
if (layout.hasErrorAlert) fails.push(`页面有错误提示: ${layout.errorText}`)
if (layout.bodyLen < 500) fails.push('页面内容过少，疑似未渲染')

// ---------- 2. 各区块取值 ----------
const dump = await page.evaluate(() => {
  const txt = (id) => (document.getElementById(id)?.innerText || '').replace(/\s+/g, ' ').trim()
  const out = { byId: {}, tables: {} }
  for (const id of ['svcTable', 'modelTable', 'cfgTable', 'dbTable', 'storeTable', 'sysTable']) {
    const el = document.getElementById(id)
    if (el) out.byId[id] = el.innerText.replace(/\s+/g, ' ').trim().slice(0, 420)
  }
  // 兜底：把页面上所有 table 的文本也抓出来（防 id 不同）
  document.querySelectorAll('table').forEach((t, i) => {
    out.tables['t' + i] = (t.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 300)
  })
  return out
})
console.log('\n=== 2. 各区块内容 ===')
for (const [k, v] of Object.entries(dump.byId)) console.log(`  [${k}] ${v.slice(0, 260)}`)
if (!Object.keys(dump.byId).length) {
  console.log('  （未按 id 抓到，改用全部表格）')
  for (const [k, v] of Object.entries(dump.tables)) console.log(`  [${k}] ${v.slice(0, 260)}`)
}

const allText = JSON.stringify(dump)
if (allText.includes('[object Object]')) fails.push('页面出现 [object Object]（对象未正确渲染）')
if (!/models_vE_r101_288/.test(allText)) fails.push('未找到集成成员 models_vE_r101_288')
if (!/ensemble|集成/.test(allText)) fails.push('未找到集成推理信息')
if (!/SQLite|sqlite/.test(allText)) fails.push('未找到数据库信息')

// ---------- 3. 全站模型清单（本轮新增） ----------
console.log('\n=== 3. 全站模型清单 ===')
const am = await page.evaluate(() => {
  const rows = [...document.querySelectorAll('#allModelsTable tr')].map((tr) => {
    const tds = [...tr.children].map((td) => td.textContent.trim().replace(/\s+/g, ' '));
    return tds.length >= 6 ? {
      status: tds[0], role: tds[1], name: tds[2], backend: tds[3], device: tds[4], detail: tds[5],
    } : { group: (tds[0] || '').trim() };
  });
  return { badge: document.getElementById('allModelsBadge')?.textContent || '', rows };
})
console.log('  角标:', am.badge)
am.rows.forEach((r) => {
  if (r.group) console.log('  --- ' + r.group + ' ---')
  else console.log(`   [${r.status}] ${r.role} | ${r.name} | ${r.backend} | ${r.device}`)
})
const modelRows = am.rows.filter((r) => r.role)
const names = modelRows.map((r) => r.name).join(' ')
if (modelRows.length < 4) fails.push(`全站模型清单条目过少（${modelRows.length}），应含图像+问答全部模型`)
if (!/models_vE_r101_288/.test(names)) fails.push('清单缺良恶性主判定模型')
if (!/models_compressed_7class|model_int8/.test(names)) fails.push('清单缺 7 类类型参考模型')
if (!/qwen3\.5:4b-med3/.test(names)) fails.push('清单缺问答文本模型 qwen3.5:4b-med3')
if (!/qwen2\.5vl/.test(names)) fails.push('清单缺问答看图模型 qwen2.5vl')
if (!/就绪/.test(am.badge)) fails.push(`清单角标异常: ${am.badge}`)
// 分组标题应在
if (!am.rows.some((r) => r.group && /图像检测/.test(r.group))) fails.push('缺「图像检测」分组标题')
if (!am.rows.some((r) => r.group && /医疗问答/.test(r.group))) fails.push('缺「医疗问答」分组标题')
console.log(`  ✔ 共 ${modelRows.length} 个模型条目，角标「${am.badge}」`)

// ---------- 4. 集成成员渲染细节 ----------
const ens = await page.evaluate(() => {
  const el = [...document.querySelectorAll('code.path')].map((c) => c.textContent.trim())
  return { pathCodes: el, hasObjObj: document.body.innerText.includes('[object Object]') }
})
console.log('\n=== 3. 集成成员渲染 ===')
console.log('  code.path 内容:', JSON.stringify(ens.pathCodes.slice(0, 8)))
console.log('  含 [object Object]:', ens.hasObjObj)
if (!ens.pathCodes.some((x) => x.includes('models_vE_r101_288'))) {
  fails.push('集成成员未渲染出模型路径')
}

await page.screenshot({ path: '/tmp/admin-system.png', fullPage: true })

console.log('\n=== 控制台错误 ===')
console.log(errs.length ? errs.join('\n') : '（无）')
if (errs.length) fails.push('存在控制台报错')

console.log('\n=== 结论 ===')
console.log(fails.length ? '✘ FAIL\n' + fails.map((f) => ' - ' + f).join('\n') : '✔ PASS —— 系统状态页正常加载')
await browser.close()
process.exit(fails.length ? 1 : 0)
