import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * 功能卡轮播（露边 + 无缝循环）
 *
 * 布局：一次显示 1 张大卡（占视口 slideRatio），左右各露邻卡 (1-slideRatio)/2。
 * 循环：DOM 里把「最后一张」克隆到队首、「第一张」克隆到队尾（共 N+2 张），
 *       滑到克隆卡后关掉过渡瞬移回真实位置 —— 因此左右两侧永远不空。
 *
 * 交互：点击圆点 / 箭头 · 鼠标触摸左右拖动 · 键盘 ←→ · 自动播放 · 悬停暂停
 *
 * @param {Array}  items        [{icon, title, desc, tone, en}]
 * @param {number} interval     自动切换毫秒（0 = 关闭）
 * @param {number} slideRatio   主卡占视口比例（默认 0.8 → 两侧各露 10%）
 * @param {number} cardMinH     卡片最小高度 px（默认 0 = 不设下限，随内容自适应）
 * @param {boolean} showEn      是否显示英文标题块（用于填充增高的卡片）
 * @param {number} dragRatio    拖动多少比例触发翻页
 */
export default function FeatureCarousel({
  items = [],
  interval = 7000,
  dragRatio = 0.18,
  slideRatio = 0.8,
  cardMinH = 0,
  showEn = false,
}) {
  // 调参预览页可通过 URL 参数实时覆盖（生产环境不带参数时行为不变）
  //   用法：/app/?carousel=slide:0.6,minH:320,en:1
  const q = (() => {
    if (typeof window === 'undefined') return {}
    const raw = new URLSearchParams(window.location.search).get('carousel')
    if (!raw) return {}
    const o = {}
    raw.split(',').forEach((kv) => {
      const [k, v] = kv.split(':')
      if (k === 'slide') o.slideRatio = parseFloat(v)
      else if (k === 'minH') o.cardMinH = parseInt(v, 10)
      else if (k === 'en') o.showEn = v === '1' || v === 'true'
    })
    return o
  })()
  if (q.slideRatio) slideRatio = q.slideRatio
  if (q.cardMinH) cardMinH = q.cardMinH
  if (q.showEn !== undefined) showEn = q.showEn

  const [index, setIndex] = useState(0)        // 逻辑索引（0..total-1）
  const [pos, setPos] = useState(1)            // DOM 位置索引（1..total），首尾各有一个克隆
  const [dragX, setDragX] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [paused, setPaused] = useState(false)
  const [reduced, setReduced] = useState(false)
  const [viewportW, setViewportW] = useState(0)
  const [instant, setInstant] = useState(false)  // 瞬移（无过渡）标志

  const trackRef = useRef(null)
  const viewportRef = useRef(null)
  const startXRef = useRef(0)
  const widthRef = useRef(0)
  const jumpTimer = useRef(null)

  const total = items.length
  const SLIDE_RATIO = slideRatio   // 主卡占视口比例
  const GAP = 6                    // 卡间每侧 margin，需与 CSS .carousel-slide margin 一致

  /** 位移步进 = 卡宽 + 左右 margin（漏掉 margin 会累积偏移） */
  const stepPx = (vpW) => vpW * SLIDE_RATIO + GAP * 2

  // 渲染列表：末张克隆 + 原列表 + 首张克隆
  const slides = total > 1
    ? [items[total - 1], ...items, items[0]].map((it, i) => ({
        ...it,
        _pos: i,                                    // DOM 位置
        _real: i === 0 ? total - 1 : i === total + 1 ? 0 : i - 1,  // 对应逻辑索引
      }))
    : items.map((it, i) => ({ ...it, _pos: i, _real: i }))

  // 尊重系统"减少动态效果"偏好
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mq) return
    const on = () => setReduced(mq.matches)
    on()
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [])

  // 测量视口宽度（露边布局与拖动阈值都依赖）
  useEffect(() => {
    const measure = () => {
      const vp = viewportRef.current
      if (!vp) return
      const w = vp.getBoundingClientRect().width
      setViewportW(w)
      widthRef.current = stepPx(w)
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  const step = stepPx(viewportW)

  /** 切换到逻辑索引 i：先做位移动画，落位后若是克隆卡则瞬移回真实位置 */
  const goTo = useCallback((i, dir) => {
    const next = ((i % total) + total) % total
    setIndex(next)

    // 判断是否需要借道克隆卡（实现无缝循环）
    const curPos = pos
    let targetPos = next + 1
    if (dir === 'next' && next === 0 && curPos === total) targetPos = total + 1  // 末 → 首：滑到尾部克隆
    if (dir === 'prev' && next === total - 1 && curPos === 1) targetPos = 0      // 首 → 末：滑到头部克隆
    setPos(targetPos)

    // 落在克隆位置上，等动画结束瞬移回真实位置
    if (targetPos !== next + 1) {
      clearTimeout(jumpTimer.current)
      jumpTimer.current = setTimeout(() => {
        setInstant(true)
        setPos(next + 1)
        // 下一帧恢复过渡
        requestAnimationFrame(() => requestAnimationFrame(() => setInstant(false)))
      }, 560)
    }
  }, [pos, total])

  // 自动播放：悬停/拖拽/减少动效时暂停
  useEffect(() => {
    if (!interval || reduced || paused || dragging || total < 2) return
    const t = setTimeout(() => goTo(index + 1, 'next'), interval)
    return () => clearTimeout(t)
  }, [index, interval, paused, dragging, reduced, total, goTo])

  useEffect(() => () => clearTimeout(jumpTimer.current), [])

  // ---------- 拖拽 ----------
  const onPointerDown = (e) => {
    if (total < 2) return
    startXRef.current = e.clientX
    setDragging(true)
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }

  const onPointerMove = (e) => {
    if (!dragging) return
    setDragX(e.clientX - startXRef.current)
  }

  const endDrag = () => {
    if (!dragging) return
    const ratio = dragX / (widthRef.current || 1)
    setDragging(false)
    setDragX(0)
    if (Math.abs(ratio) >= dragRatio) {
      goTo(ratio < 0 ? index + 1 : index - 1, ratio < 0 ? 'next' : 'prev')
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'ArrowRight') { goTo(index + 1, 'next'); e.preventDefault() }
    if (e.key === 'ArrowLeft') { goTo(index - 1, 'prev'); e.preventDefault() }
  }

  if (!total) return null

  // 位移：pos 从 0 开始，公式同前（+GAP×2 抵消卡自身左 margin）
  const shift = -(pos * step + GAP * 2) + dragX

  return (
    <div
      className="carousel"
      role="region"
      aria-roledescription="轮播"
      aria-label="系统功能"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      onKeyDown={onKeyDown}
      tabIndex={0}
    >
      <div
        ref={viewportRef}
        className={`carousel-viewport${dragging ? ' is-dragging' : ''}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div
          ref={trackRef}
          className="carousel-track"
          style={{
            transform: `translate3d(${shift}px, 0, 0)`,
            transition: (dragging || instant) ? 'none' : 'transform .55s cubic-bezier(.22,1,.36,1)',
          }}
        >
          {slides.map((s) => {
            // 只让「当前 DOM 位置」的卡高亮（克隆卡与原卡 _real 相同，需按 pos 判定）
            const active = s._pos === pos
            return (
              <div
                key={`${s._pos}-${s.title}`}
                data-slide
                data-pos={s._pos}
                className={`carousel-slide${active ? ' is-active' : ''}`}
                aria-hidden={!active}
                style={{ width: viewportW ? `${viewportW * SLIDE_RATIO}px` : '80%' }}
              >
                <article
                  className={`feature-card tone-${s.tone || 'blue'}`}
                  style={cardMinH ? { minHeight: `${cardMinH}px` } : undefined}
                >
                  <div className="feature-card-icon" aria-hidden="true">{s.icon}</div>
                  <div className="feature-card-body">
                    <h3 className="feature-card-title">{s.title}</h3>
                    {showEn && s.en && (
                      <p className="feature-card-en" aria-hidden="true">{s.en}</p>
                    )}
                    <p className="feature-card-desc">{s.desc}</p>
                    {showEn && s.descEn && (
                      <p className="feature-card-desc-en" lang="en">{s.descEn}</p>
                    )}
                  </div>
                  <div className="feature-card-no" aria-hidden="true">
                    {String(s._real + 1).padStart(2, '0')}
                    <span className="feature-card-no-total">/ {String(total).padStart(2, '0')}</span>
                  </div>
                </article>
              </div>
            )
          })}
        </div>
      </div>

      {/* 控制条 */}
      <div className="carousel-footer">
        <div className="carousel-dots" role="tablist" aria-label="切换功能卡片">
          {items.map((it, i) => (
            <button
              key={it.title}
              type="button"
              role="tab"
              aria-selected={i === index}
              aria-label={`第 ${i + 1} 张：${it.title}`}
              title={it.title}
              onClick={() => goTo(i)}
              className={`carousel-dot${i === index ? ' is-active' : ''}`}
            >
              {i === index && interval > 0 && !reduced && (
                <span
                  className={`carousel-dot-fill${paused || dragging ? ' is-paused' : ''}`}
                  style={{ animationDuration: `${interval}ms` }}
                />
              )}
            </button>
          ))}
        </div>

        <div className="carousel-nav">
          <button type="button" className="carousel-arrow"
            onClick={() => goTo(index - 1, 'prev')} aria-label="上一张">←</button>
          <span className="carousel-count">
            {index + 1} <span className="opacity-50">/ {total}</span>
          </span>
          <button type="button" className="carousel-arrow"
            onClick={() => goTo(index + 1, 'next')} aria-label="下一张">→</button>
        </div>
      </div>

      <p className="carousel-hint">
        ← 拖动卡片或点击圆点切换 · 共 {total} 项功能 →
      </p>
    </div>
  )
}
