import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * 检测流程展示 · 单框缩放镜头
 *
 * 一个框内：4 个步骤块按四象限摆放，用闭环箭头串成环（①→②→③→④→①）。
 * 默认 = 全景小图（每块只有图标 + 标题 + 淡光）；
 * 点击左侧数字 → 镜头放大推进到对应块（块内展开完整动态演示，
 *   同时保留一圈闭环箭头痕迹，表明它仍在环里）。
 *
 * @param {Array}  steps     [{title, desc, stage, icon}]
 * @param {number} interval  自动播放毫秒（0 = 关闭）
 */

// 四象限布局（块中心的百分比坐标）：左上→右上→右下→左下，顺时针
// 配合 .proc-block 的 38%×24%，块占位：x8~46 / x54~92，y20~44 / y52~76
// → 水平通道 46~54、垂直通道 44~52（各留 8%，弧线从中间绕行不碰块）
const LAYOUT = [
  { x: 27, y: 32 },   // 0 上传（左上）
  { x: 73, y: 32 },   // 1 预处理（右上）
  { x: 73, y: 64 },   // 2 推理（右下）
  { x: 27, y: 64 },   // 3 解读（左下）
]

/**
 * 闭环：一个完整的大椭圆，精确穿过 4 个演示块的中心。
 *   椭圆中心 (50,48)、半轴 rx=32.5 ry=22.6
 *   → 4 块中心 (27,32) (73,32) (73,64) (27,64) 都满足椭圆方程 = 1.000
 * 箭头摆在各块之间的空档（椭圆参数 270°/0°/90°/180°），沿切线方向，不碰到块。
 */
const ELLIPSE = { cx: 50, cy: 48, rx: 37.5, ry: 26 }

// 光束沿椭圆循环的路径（两条半椭圆弧拼成整圈）
const ELLIPSE_PATH = 'M 87.5 48 A 37.5 26 0 1 1 12.5 48 A 37.5 26 0 1 1 87.5 48'

const LOOP_ARROWS = [
  { x: 50.0, y: 22.0, r: 0.0 },      // 上（离块 13.5px 间隙）
  { x: 87.5, y: 48.0, r: 90.0 },     // 右（离块 8.5px 间隙）
  { x: 50.0, y: 74.0, r: 180.0 },    // 下
  { x: 12.5, y: 48.0, r: -90.0 },    // 左
]

export default function ProcessShowcase({ steps = [], interval = 9000, heading, subheading }) {
  const [active, setActive] = useState(0)    // 当前高亮步骤
  const [picked, setPicked] = useState(false) // 是否已点击过步骤（未点 = 缩略态）
  const [inView, setInView] = useState(false) // 演示区是否已滚入视口
  const stageRef = useRef(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  const zoomTimer = useRef(null)

  const total = steps.length

  const go = useCallback((i) => {
    setActive(((i % total) + total) % total)
    setPicked(true)
  }, [total])

  // 测展示框尺寸（缩放位移需要精确像素）
  useEffect(() => {
    const measure = () => {
      const el = stageRef.current
      if (el) {
        const r = el.getBoundingClientRect()
        setBox({ w: r.width, h: r.height })
      }
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  useEffect(() => () => clearTimeout(zoomTimer.current), [])

  // 滚入视口 → 停留 1 秒后自动开始轮播（先展示第 1 步，再逐步推进）
  // ⚠️ 只在首次进入时触发一次（started 一旦为 true 就不再打断用户的点击选择）
  const started = useRef(false)
  useEffect(() => {
    const el = stageRef.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => setInView(en.isIntersecting))
      },
      // 阈值 0.45：演示区露出近一半才算"滚到这里"，避免刚探个头就开播
      { threshold: 0.45 }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!inView || started.current) return
    started.current = true
    // 停 1 秒 → 进入第 1 步的放大演示（picked=true 触发镜头推进），
    // 之后由下面的自动播放 effect 每 interval 毫秒推进到下一步
    const t = setTimeout(() => setPicked(true), 1000)
    return () => clearTimeout(t)
  }, [inView])

  // 自动播放：逐步推进，末步后循环回第 1 步
  useEffect(() => {
    if (!interval || total < 2 || !picked) return
    const t = setTimeout(() => go(active + 1), interval)
    return () => clearTimeout(t)
  }, [active, interval, total, go, picked])

  const onKeyDown = (e) => {
    if (e.key === 'ArrowRight') { go(active + 1); e.preventDefault() }
    if (e.key === 'ArrowLeft') { go(active - 1); e.preventDefault() }
  }

  if (!total) return null

  // 用户是否点过步骤（未点过 = 看全 4 块的缩略态）
  // 默认缩略态看全 4 块；点数字后放大到对应块
  const target = LAYOUT[active]
  const tx = picked && box.w ? box.w / 2 - (target.x / 100) * box.w * ZOOM : 0
  const ty = picked && box.h ? box.h / 2 - (target.y / 100) * box.h * ZOOM : 0

  return (
    <div
      className="process"
      onKeyDown={onKeyDown}
      tabIndex={0}
      role="region"
      aria-label="检测流程演示"
    >
      {/* 左：标题 + 步骤列表（与右侧演示框同栏，顶底对齐） */}
      <div className="process-left">
        {(heading || subheading) && (
          <header className="process-head">
            {heading && <h2 className="section-heading">{heading}</h2>}
            {subheading && <p className="section-subheading">{subheading}</p>}
          </header>
        )}
          <ol className="process-steps" role="tablist" aria-label="检测流程步骤">
          {steps.map((s, i) => (
            <li key={s.title} className="process-step-item">
              <button type="button" role="tab" aria-selected={i === active}
                onClick={() => go(i)}
                className={`process-step${i === active ? ' is-active' : ''}`}>
                <span className="process-step-no">{String(i + 1).padStart(2, '0')}</span>
                <span className="process-step-body">
                  <span className="process-step-title">{s.title}</span>
                  {i === active && <span className="process-step-desc">{s.desc}</span>}
                </span>
                <span className="process-step-track">
                  <span className="process-step-fill"
                    style={i === active && interval ? { animationDuration: `${interval}ms` } : undefined} />
                </span>
              </button>
            </li>
            ))}
          </ol>
      </div>

      {/* 右：单框 + 缩放镜头 */}
      <div className={`process-stage${picked ? ' is-zoomed' : ''}`} ref={stageRef}>
        {/* 网格纹理 */}
        <svg className="process-grid" aria-hidden="true">
          <defs>
            <pattern id="proc-grid" width="44" height="44" patternUnits="userSpaceOnUse">
              <path d="M 44 0 L 0 0 0 44" fill="none" stroke="currentColor" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#proc-grid)" />
        </svg>

        {/* 世界画布：默认 100%，放大时 scale */}
        <div
          className={`proc-world${picked ? ' is-zoom' : ''}`}
          style={{
            transform: `translate3d(${tx}px, ${ty}px, 0) scale(${picked ? ZOOM : 1})`,
          }}
        >
          {/* 闭环层：一个大椭圆穿过 4 块中心 + 沿切线的箭头 + 单个流动光点 */}
          <svg className="proc-loop" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <ellipse
              className="proc-loop-ellipse"
              cx={ELLIPSE.cx} cy={ELLIPSE.cy} rx={ELLIPSE.rx} ry={ELLIPSE.ry}
              fill="none" stroke="#7fc4e8" strokeWidth=".42"
              strokeDasharray="1.5 1.1"
            />
            {/* 箭头：缩小一倍（长 2.2），开放式两斜线 */}
            {LOOP_ARROWS.map((ar, i) => (
              <path
                key={i}
                className="proc-loop-arrow"
                d="M -1.1 -0.7 L 1.1 0 L -1.1 0.7"
                fill="none" stroke="#cfeeff" strokeWidth=".42"
                strokeLinecap="round" strokeLinejoin="round"
                transform={`translate(${ar.x} ${ar.y}) rotate(${ar.r})`}
                style={{ animationDelay: `${i * 0.6}s` }}
              />
            ))}
            {/* 单个引导光点：沿椭圆循环流动 */}
            <circle className="proc-loop-dot" r=".85">
              <animateMotion dur="10s" repeatCount="indefinite" rotate="auto" path={ELLIPSE_PATH} />
            </circle>
          </svg>

          {/* 四个步骤块 */}
          {steps.map((s, i) => (
            <div
              key={s.title}
              className={`proc-block${i === active ? ' is-active' : ''}`}
              style={{ left: `${LAYOUT[i].x}%`, top: `${LAYOUT[i].y}%` }}
              onClick={() => go(i)}
            >
              {/* 小图态：图标 + 序号 + 标题 */}
              <div className="proc-block-mini">
                <span className="proc-block-icon" aria-hidden="true">{s.icon}</span>
                <span className="proc-block-mini-title">{s.title}</span>
                <span className="proc-block-mini-no">{String(i + 1).padStart(2, '0')}</span>
              </div>
              {/* 放大态：完整动态演示 */}
              <div className="proc-block-full">
                <span className="proc-block-full-title">{s.title}</span>
                {i === 0 && <SceneUpload />}
                {i === 1 && <ScenePreprocess />}
                {i === 2 && <SceneInference />}
                {i === 3 && <SceneResult />}
              </div>
            </div>
          ))}
        </div>

        {/* 底部状态条 */}
        <div className="process-stage-foot">
          <span className="process-stage-dot" />
          <span>{picked ? steps[active]?.stage : 'Overview · Closed Loop'}</span>
        </div>

        {!picked && (
          <div className="process-hint">点击左侧步骤，镜头将放大进入对应演示</div>
        )}
      </div>
    </div>
  )
}

const ZOOM = 2.3

/* ---------- 各步动态演示（放大态展示） ---------- */
function SceneUpload() {
  return (
    <div className="sc sc-upload">
      <div className="sc-drop">
        <svg viewBox="0 0 24 24" className="sc-drop-icon" aria-hidden="true">
          <path d="M12 16V4m0 0L8 8m4-4 4 4" fill="none" stroke="currentColor" strokeWidth="1.6"
            strokeLinecap="round" strokeLinejoin="round" />
          <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" fill="none" stroke="currentColor"
            strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <span>拖拽或点击上传</span>
      </div>
      <div className="sc-thumbs">
        {[0, 1, 2].map((i) => (
          <span key={i} className="sc-thumb" style={{ animationDelay: `${0.5 + i * 0.35}s` }}>
            <Skin />
          </span>
        ))}
      </div>
    </div>
  )
}

function ScenePreprocess() {
  return (
    <div className="sc sc-pre">
      <div className="sc-pre-wrap">
        <div className="sc-pre-img"><Skin /></div>
        <span className="sc-pre-scan" />
        <span className="sc-pre-mesh" />
      </div>
      <div className="sc-meta">
        <span className="sc-chip">Resize</span>
        <span className="sc-eq">→</span>
        <span className="sc-chip sc-chip-strong">288 × 288</span>
      </div>
    </div>
  )
}

function SceneInference() {
  const nodes = [
    { x: 12, y: 22 }, { x: 12, y: 50 }, { x: 12, y: 78 },
    { x: 42, y: 15 }, { x: 42, y: 42 }, { x: 42, y: 68 }, { x: 42, y: 92 },
    { x: 72, y: 32 }, { x: 72, y: 64 },
    { x: 94, y: 48 },
  ]
  const edges = [
    [0, 3], [0, 4], [1, 3], [1, 4], [1, 5], [2, 4], [2, 5], [2, 6],
    [3, 7], [4, 7], [4, 8], [5, 8], [6, 8], [7, 9], [8, 9],
  ]
  return (
    <div className="sc sc-net">
      <svg viewBox="0 0 100 100" className="sc-net-svg" preserveAspectRatio="none" aria-hidden="true">
        {edges.map(([a, b], i) => (
          <line key={i} x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y}
            className="net-edge" style={{ animationDelay: `${i * 0.07}s` }} />
        ))}
        {nodes.map((n, i) => (
          <circle key={i} cx={n.x} cy={n.y} r="1.6" className="net-node"
            style={{ animationDelay: `${i * 0.12}s` }} />
        ))}
      </svg>
      <div className="sc-meta">
        <span className="sc-chip">ResNet50 + ResNet101</span>
        <span className="sc-chip sc-chip-live"><span className="sc-pulse" />Ensemble</span>
      </div>
    </div>
  )
}

function SceneResult() {
  return (
    <div className="sc sc-result">
      <div className="sc-bar-row">
        <span className="sc-bar-label">恶性</span>
        <span className="sc-bar-track"><span className="sc-bar-fill sc-bar-mal" /></span>
        <span className="sc-bar-val">87.4%</span>
      </div>
      <div className="sc-bar-row">
        <span className="sc-bar-label">良性</span>
        <span className="sc-bar-track"><span className="sc-bar-fill sc-bar-ben" /></span>
        <span className="sc-bar-val">12.6%</span>
      </div>
      <ul className="sc-types">
        {['黑色素瘤', '黑色素细胞痣', '基底细胞癌'].map((t, i) => (
          <li key={t} className="sc-type" style={{ animationDelay: `${0.5 + i * 0.25}s` }}>
            <span className="sc-type-tick" />{t}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Skin() {
  return (
    <svg viewBox="0 0 40 40" className="sc-skin" aria-hidden="true">
      <rect width="40" height="40" rx="6" fill="#2a4a63" />
      <ellipse cx="20" cy="21" rx="9" ry="7.5" fill="#8a6a52" />
      <ellipse cx="20" cy="21" rx="4.6" ry="3.6" fill="#5d4033" />
      <ellipse cx="18.6" cy="20" rx="1.5" ry="1.1" fill="#3f2a21" opacity=".85" />
    </svg>
  )
}
