// 从 src/components/planeGeometry.js 同步几何/姿态/渲染代码到 public/plane-preview.html
// 保证调参页与网页共用同一份渲染逻辑（所见即所得）
import fs from 'fs'
import path from 'path'

const root = path.resolve('.')
const geoPath = path.join(root, 'src/components/planeGeometry.js')
const prevPath = path.join(root, 'public/plane-preview.html')

let geo = fs.readFileSync(geoPath, 'utf8')

// 去掉 export 关键字，转成普通声明供 <script> 使用
geo = geo
  .replace(/^export\s+const\s+/gm, 'const ')
  .replace(/^export\s+function\s+/gm, 'function ')
  .replace(/^export\s+const\s+(\w+)\s*=/gm, 'const $1 =')
  .replace(/export\s+function\s+/g, 'function ')
  .replace(/export\s+const\s+/g, 'const ')

// 提取需要注入的部分（整个文件去掉注释头即可）
const marker = '/* __GEO_START__ */'
const endMarker = '/* __GEO_END__ */'

let html = fs.readFileSync(prevPath, 'utf8')
if (!html.includes(marker)) {
  console.log('⚠️  预览页里没有注入标记，跳过同步（需先改造预览页）')
  process.exit(0)
}
const before = html.split(marker)[0]
const after = html.split(endMarker)[1]

html = before + marker + '\n' + geo + '\n' + endMarker + after
fs.writeFileSync(prevPath, html)
console.log('✅ 预览页已从 planeGeometry.js 同步（共 ' + geo.split('\n').length + ' 行）')
