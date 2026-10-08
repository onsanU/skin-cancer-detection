# Hero 首屏动效改造工作记录

> 日期：2026-09-15（晚）
> 范围：主页首屏（hero）视觉与交互动效 + 登录/注册跳转 + 缓存修复
> 状态：已完成并通过验证，服务已关闭

---

## 一、本次改造要解决的问题

1. 登录页「← 返回首页」按钮位置错误（挤在左半边，未按设计放右上角）
2. 登录/注册成功后直接跳到图像检测页，期望跳回主页
3. 主页 hero 区想复刻 Trajectory.ai 的视觉风格（渐变 + 点阵云 + 纸飞机 + 金色粒子拖尾 + 滚动叙事）

---

## 二、逐项改动明细

### 2.1 登录页布局修复

**问题根因**：`.auth-page` 用 `display: grid` 做左右分栏（45:55），但它的直接子元素其实是
`<header>` / `<main>` / `<footer>` 三个 —— header 和 footer 被 grid 当成独立的"列"参与排版，
导致 header 宽度塌成内容宽度（363px），内部的 `justify-between` 无处发挥，
logo 与「返回首页」按钮只能挤在一起。

**修复方案**：
- `.auth-page` 改为 `display: flex; flex-direction: column`（普通纵向流式容器）
- 左右分栏下沉到 `<main>` 上的新类 `.auth-split`
- 两个 `<section>` 作为 `.auth-split` 的直接子元素（**保证只有一层分栏**）

**踩过的坑（重要）**：
- 第一轮只加了 `.auth-split`、**忘了删内层的 Tailwind grid**，造成双重分栏：
  外层切出 576px 给左栏，内层又把这 576px 按 45:55 切成 230/282px，
  结果标题只剩 230px 宽，59px 的巨字被迫逐字断行成 5 行、表单卡片被压窄。
  → **分栏容器只能有一层**。

**涉及文件**：
| 文件 | 改动 |
|---|---|
| `frontend/src/index.css` | `.auth-page` 改 flex + 新增 `.auth-split`（含响应式 gap、`prefers-reduced-motion` 分支） |
| `frontend/src/components/AuthLayout.jsx` | `<main>` 加 `auth-split w-full`，去掉内层重复 grid |

**验证数据（无头浏览器实测）**：
```
修复前：header w=363px / A行 x=158 / B行 x=852（相隔 694px）
修复后：header w=1360px / 左元素 5.3% ~ 右元素 94.2%（左右分离）
        窄屏 800px：header 792px 可见、左文案区正确隐藏
```

---

### 2.2 登录/注册后跳转主页

**需求**：登录或注册成功后回到主页 `/`，而不是直接进图像检测页；
但「被拦截后跳登录」的场景要保留来路（如从 /history 被拦 → 登录后回 /history）。

**改动**：
| 文件 | 改动 |
|---|---|
| `frontend/src/pages/LoginPage.jsx` | `from` 默认值 `/detect` → `/`；「立即注册」链接带上 `state={{ from }}` |
| `frontend/src/pages/RegisterPage.jsx` | 引入 `useLocation`，加 `from` 逻辑（默认 `/`）；`navigate('/detect')` → `navigate(from)`；「去登录」链接带 `state={{ from }}` |

**行为规则**：
```
直接从登录/注册页进来       → 回主页 /
从 /history 被拦去登录再登  → 回 /history
登录 ↔ 注册 互相跳转        → 来路一直带着
```

**验证（无头浏览器真填表真点按钮）**：
```
场景1 起点 /app/login  → 填表登录 → 落地 /app/          ✓
场景2 访问 /app/history → 被拦到登录 → 登录 → 落地 /app/history ✓
```

---

### 2.3 静态资源缓存修复（顺手治本）

**问题**：`index.html` 本身没有内容哈希，浏览器会强缓存它；
一旦用户缓存了旧版 html，它引用的旧 assets 就会一直生效，
即使 dist 已重新构建、页面结构已更新，用户看到的仍是老界面。
（本次「改了页面但浏览器显示旧版」就是这么来的）

**改动**（`backend/app/main.py`）：
```python
# index.html：禁用缓存（保证每次回源拿到最新引用）
Cache-Control: no-cache, no-store, must-revalidate
# assets/*（文件名带内容哈希）：长期缓存
Cache-Control: public, max-age=31536000, immutable
```

---

### 2.4 Hero 首屏动效改造（本次主体工作量）

#### 素材提取

从 trajectory.ai 首页提取并优化：

| 素材 | 处理 | 体积 |
|---|---|---|
| 渐变大背景 `viz-platform.png` | 压缩为 `hero-bg.jpg` | 391KB → 108KB |
| 点阵云 ×3（`cloud-source-*.png`） | 压缩改名 `cloud-1/2/wide.png` | 压缩至 256 色索引 PNG |
| 纸飞机 | **WebGL 3D 网格，非图片** | 从 JS 里 Base64 解码取得 |

**素材总体积：3.8MB → 384KB（减少约 90%）**

**纸飞机网格提取细节**：
```
原站用 WebGL 渲染 3D 纸飞机，网格数据以 Base64 内嵌在 JS chunk 里。
解码后 = 43 个顶点 / 20 个三角形（顶点内含位置 + 法线）
模型坐标系：+Z = 机身纵轴（-3.5 端是尖端机头，+1.5 端是宽面机尾）
```
> 注：一开始误判了机头方向（以为 +Z 是机头），
> 后通过「比较两端顶点的横向跨度」客观判定：跨度 0 的是尖机头、跨度 3.98 的是宽机尾。

#### 新增文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `frontend/src/components/planeGeometry.js` | 161 | **唯一渲染源**：网格数据 + 姿态参数 + `computePose()` + `renderPlane()` + `noseAngle()` |
| `frontend/src/components/HeroPlane.jsx` | 400 | 纸飞机 + 金色粒子拖尾动画层（canvas 实时渲染） |
| `frontend/public/plane-preview.html` | 299 | **实时调参页**（拖滑块调姿态，所见即所得） |
| `frontend/scripts_sync_preview.mjs` | 40 | 构建前把 `planeGeometry.js` 注入调参页，保证两边同源 |

#### 渲染实现要点

**纸飞机（Canvas 2D 软件光栅化）**
```
· 透视投影（camDist 6.5，透视系数 0.30）
· 双面平面着色（背面翻转法线）
· 机身三段纵向渐变：尾部淡粉紫 #ECD5E4 → 中段淡粉 #F7E6E8 → 机头近白 #FDF4F0
· 背光面往粉紫阴影 #C9A8C4 靠（纸张暗面带环境色，不是纯黑）
· Fresnel 边缘光 #8A6CB8（复刻原站着色器 rim light）
· 画家算法深度排序（远→近）
```

**金色粒子拖尾（12000 粒子）**
```
· 粒子沿 trailAngle 方向铺成"粒子带"，每个粒子有独立目标点
· 弹簧 + 阻尼追向目标点：trailSpring 0.18 / trailDamp 0.80
  （实测：0.10→跟踪误差 7.77px、0.18→2.20px、0.28→7.60px、0.40→9.25px
   —— 弹簧过硬反而过冲振荡，0.18 为实测最优）
· 加法混合 globalCompositeOperation='lighter' 产生发光感
· 亮度随"离起点距离"和"离轴距离"衰减 → 新亮旧淡的尾巴
· 颜色：核心金 #FFDF78 → 边缘橙金 #E8A858
· 鼠标交互：90px 半径内推开粒子（cursorForce 50）
· 入场后整条粒子带随飞机每帧同步平移 → 始终紧贴机尾
```

**滚动叙事（三阶段，由 `--hero-prog` 驱动）**
```
prog 0.00-0.55  两行巨字「洞察入微」「防患未然」向中间靠拢、合并成一行
prog 0.55-0.75  停在原地不动
prog 0.75-1.00  滚到 hero 底部时整行慢慢淡出
同时：纸飞机向右上飞离 + 缩小至 45% + 淡出
      说明文字/按钮/状态卡分档淡出（快速组先退场）
```
> 实现方式：React 写 `--hero-prog`（0→1），CSS 用变量派生 `--p-merge` / `--p-fade`
> 驱动 transform/opacity（合成层动画，不触发重排）。
> 两行合并所需的位移量由 JS **实测文字宽度**算出（`--shift-ax` / `--shift-bx`），
> 任何视口都能精确对齐，不依赖魔法百分比。

**云朵缓慢左右浮动**
```
三朵云各挂一个 CSS 动画，幅度 ±12~18px、周期 22~30s、相位错开（负延迟）
尊重 prefers-reduced-motion（晕动症用户自动关闭）
```

#### 解决的核心难题：调参页与网页不一致

**问题**：调参页（HTML）和网页组件（JSX）各自写了一份渲染逻辑，
参数含义/旋转顺序会悄悄漂移 → **「调参页调好、搬到网页就变样」**，
导致姿态反复调不准、来回折腾多轮。

**解决方案**：抽出 `planeGeometry.js` 作为唯一渲染源，两边共用：
```
HeroPlane.jsx      → import { computePose, renderPlane, PLANE_POSE }
plane-preview.html → 构建前由 scripts_sync_preview.mjs 注入同一份代码
```

**一致性验证（决定性证据）**：
```
网页姿态   机头方向 45.00°  fitR 0.9159
预览页姿态 机头方向 45.00°  fitR 0.9159
顶点最大差异 0.000e+0
→ 两边渲染姿态完全一致（所见即所得）
```

**最终姿态参数**（主人用调参页确认）：
```js
PLANE_POSE = { rot90: 90, yaw: 135, pitch: 90, roll: -20 }
微调: extraZ: 111, extraY: 6, extraX: 90
```
联动修正：拖尾方向 `trailAngle` 由机头/机尾屏幕方向反推 = **126°**
（改姿态后必须重算，否则粒子会飘到机头前方变成"倒着飞"）

---

## 三、验证方式汇总

| 验证项 | 方法 | 结果 |
|---|---|---|
| 布局 | 无头浏览器注入探针，读 `getBoundingClientRect` | header 363px → 1360px |
| 跳转 | 无头浏览器真填表、真点按钮，读最终 `location.pathname` | 两场景全通过 |
| 构建 | `npm run build` | ✓ 103 modules |
| 几何 | 离线用同一套算法渲染 + 像素级方向检测 | 机头方向 45°，无破面 |
| 姿态一致性 | Node 比对网页/调参页顶点数组 | 差异 0.000e+0 |
| 粒子跟随 | Node 数值模拟弹簧跟踪误差 | 2.20px（贴紧） |
| 渲染逻辑 | Node stub canvas 跑 30 帧，统计绘制调用 | arc=348000（=12000×29），NaN=0 |
| 服务 | 服务返回资产 vs 磁盘产物比对 + 8 个地址连通性 | 全部一致 + 全 200 |

**验证盲区（如实说明）**：
Chrome 无头模式的 `requestAnimationFrame` 被冻结（实测 500ms 内触发 0 次），
因此**canvas 实时动画的最终观感无法通过截图验证**，需在真实浏览器查看。

---

## 四、方法论沉淀（本项目踩坑总结）

1. **CSS 分栏容器只能有一层**：grid 分栏若放在含 header/footer 的父级，
   它们会被当作独立列；重复嵌套分栏会把内容二次切窄。
2. **flex 子项带 `margin:auto` 会抑制 cross 轴 stretch**：
   容器里的元素若带 `mx-auto`，宽度会塌成内容宽度而非撑满。
3. **UI 无缓存陷阱**：`index.html` 必须禁缓存，带哈希的 assets 才可长期缓存。
4. **3D 姿态靠推导必翻车**：旋转矩阵符号约定极易搞反，
   必须"渲染出来看"或用客观判据（顶点屏幕方向角）验证。
5. **视觉调整要给用户实时调参工具**：
   做实时预览页让用户自己拖滑块，比开发者反复猜、来回构建高效得多。
6. **调参工具与生产代码必须同源**：
   各写一份必然漂移，抽出共享模块是唯一可靠解。
7. **参数改了要检查所有联动项**：飞机姿态变了，拖尾方向必须同步重算。

---

## 五、文件清单

**新增**
```
frontend/src/components/planeGeometry.js     161 行   唯一渲染源
frontend/src/components/HeroPlane.jsx        400 行   飞机+粒子动画层
frontend/public/plane-preview.html           299 行   实时调参页
frontend/scripts_sync_preview.mjs             40 行   调参页同步脚本
frontend/public/images/hero-bg.jpg           108 KB   渐变背景
frontend/public/images/cloud-1.png            88 KB   点阵云（左）
frontend/public/images/cloud-2.png            56 KB   点阵云（右）
frontend/public/images/cloud-wide.png        132 KB   点阵云（下）
```

**修改**
```
frontend/src/pages/HomePage.jsx       hero 布局重构 + 滚动进度驱动
frontend/src/index.css                auth 布局修复 + hero 动效样式
frontend/src/pages/LoginPage.jsx      跳转目标改主页 + 来路透传
frontend/src/pages/RegisterPage.jsx   同上
frontend/src/components/AuthLayout.jsx 分栏层级修正
backend/app/main.py                   静态资源缓存策略
```

---

## 六、使用说明

**启动服务**
```bash
cd 皮肤癌图像检测系统
bash start.sh          # 或双击 启动服务.bat
```

**访问地址**
```
主页（看动效）  http://127.0.0.1:8000/app/
登录页          http://127.0.0.1:8000/app/login
调参页（备用）  http://127.0.0.1:8000/app/plane-preview.html
管理后台        http://127.0.0.1:8000/admin/
API 文档        http://127.0.0.1:8000/docs
```

**后续想再调飞机姿态**
```
① 打开 plane-preview.html 拖滑块
② 满意后复制底部「PLANE_POSE = {...}」那行
③ 贴进 frontend/src/components/planeGeometry.js
④ 重算 trailAngle（拖尾方向）并同步到 HeroPlane.jsx 的 CFG
⑤ npm run build 重新构建
```
