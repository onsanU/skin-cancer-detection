import { useEffect, useRef } from 'react'

/* 纸飞机的网格、姿态与渲染逻辑全部来自共享模块 planeGeometry.js ——
   plane-preview.html 调参页也用同一份，保证「预览所见 = 网页所得」。
   历史教训：两边各写一份渲染代码时，参数含义/旋转顺序会悄悄漂移，
   导致「调参页调好了、搬到网页里就变样」。 */
import {
  PLANE_POS,
  PLANE_POSE,
  computePose,
  noseAngle,
  renderPlane,
} from './planeGeometry'

/**
 * HeroPlane —— hero 区的「纸飞机 + 金色粒子拖尾」动画层
 *
 * 灵感与算法来源：trajectory.ai 首页 hero（已提取其参数与物理逻辑）。
 * 复刻要点：
 *  1) 粒子沿 225° 方向铺成一条「粒子带」（不是实时跟随飞机位置），
 *     每个粒子有独立的目标点，靠弹簧+阻尼被拉向目标点，因此拖尾自然飘逸。
 *  2) 滚动 / 鼠标都会扰动粒子：滚动反向推、鼠标按距离平方衰减推开（trailCursorForce）。
 *  3) 加法混合（globalCompositeOperation='lighter'）产生发光感；
 *     亮度随「离起点距离」和「离轴距离」衰减，做出新亮旧淡的尾巴。
 *  4) 纸飞机用 2D 造型 + 3D 倾斜透视手绘，入场后轻微浮动，随滚动漂移。
 *
 * 该组件自带 pointer-events 管理，不会拦截 hero 区按钮的点击。
 */

// ---- 参数（取自原站，保持观感一致） ----
const CFG = {
  trailWidth: 900,
  trailHeight: 900,
  trailAngle: 126,          // 拖尾延伸方向（屏幕坐标，0=右 顺时针为正）
                            // 由机头/机尾顶点的屏幕方向反推：机头朝 53.9°（右上），
                            // 拖尾须从机尾继续往反方向延伸，否则会变成"粒子飘在机头前面"。
                            // ⚠️ 改 PLANE_POSE 后必须重算此值。
  trailLengthFactor: 0.82,  // 拖尾长度 = 宽度 × 该系数
  trailSpreadFactor: 0.16,  // 垂直扩散宽度系数
  trailCoreColor: '#FFDF78',// 金色核心
  trailEdgeColor: '#E8A858',// 橙金边缘
  trailParticleCount: 12000,
  trailParticleSize: 1.8,
  trailSpring: 0.18,        // 弹簧回位强度（实测最优：0.18 时跟踪误差最小 2.2px；
                            // 过大反而过冲振荡，误差升到 7-9px）
  trailDamp: 0.80,          // 速度阻尼
  trailCursorRadius: 90,    // 鼠标影响半径
  trailCursorForce: 50,     // 鼠标推力
  trailOriginOffsetX: -40,  // 粒子带起点（相对画布中心）：对准机尾
  trailOriginOffsetY: 40,   // 机头朝右上，机尾在左下 → 起点往左下推
  // 纸飞机
  planeSize: 3.6,
  planeDisplaySize: 446,    // 屏幕直径(px)：对齐原站 clamp(280px, 31vw, 460px) 在 1440 视口的值
  bodyAngle: 132,           // 机头朝右上（132-180 = -48°，逆时针抬起 48°）
  barrelRoll: 10,
  tiltAway: -55,
  tiltSide: -3,
  baseTailColor: '#FFFAEE',
  baseNoseColor: '#FDEBC9',
  ambientColor: '#8C80A6',
  lightColor: '#B3926E',
  rimColor: '#6B478C',
  bobIntensity: 1,
}

function hexToRgb(hex) {
  const t = hex.slice(1)
  return [
    parseInt(t.slice(0, 2), 16),
    parseInt(t.slice(2, 4), 16),
    parseInt(t.slice(4, 6), 16),
  ]
}

/** 生成粒子系统：沿拖尾方向铺开成一条带，返回各属性数组 */
function buildParticles(count, w, h, cfg) {
  const P = {
    // 目标点（弹簧拉向的位置）
    tx: new Float32Array(count),
    ty: new Float32Array(count),
    // 当前位置
    px: new Float32Array(count),
    py: new Float32Array(count),
    // 速度
    vx: new Float32Array(count),
    vy: new Float32Array(count),
    r: new Uint8ClampedArray(count),
    g: new Uint8ClampedArray(count),
    b: new Uint8ClampedArray(count),
    life: new Uint8ClampedArray(count),
    size: new Float32Array(count),
    cursorR: new Float32Array(count),
    springW: new Float32Array(count),
    tangent: new Float32Array(count),
  }

  const theta = (cfg.trailAngle * Math.PI) / 180
  const ct = Math.cos(theta)
  const st = Math.sin(theta)

  const len = w * cfg.trailLengthFactor
  const spread = w * cfg.trailSpreadFactor
  const core = hexToRgb(cfg.trailCoreColor)
  const edge = hexToRgb(cfg.trailEdgeColor)

  // 拖尾起点（画布中心 + 偏移）
  const ox = w / 2 + cfg.trailOriginOffsetX
  const oy = h / 2 + cfg.trailOriginOffsetY

  let n = 0
  const maxTries = count * 4
  for (let tries = 0; n < count && tries < maxTries; tries++) {
    // 沿轨迹位置：0=起点（亮）→1=末端（淡），偏向前段
    const e = Math.pow(Math.random(), 0.55)
    const t = e * len
    // 横向扩散：高斯分布，尾部略收
    const a = Math.pow(e, 0.5) * (1 - 0.15 * Math.pow(e, 4)) * spread
    const rnd = Math.sqrt(-2 * Math.log(Math.random() || 0.001)) *
      Math.cos(2 * Math.PI * Math.random()) * a * 0.45

    const x = ox + ct * t + -st * rnd
    const y = oy + st * t + ct * rnd

    const off = Math.min(1, Math.abs(rnd) / (a + 0.1))
    const jitter = 0.12 * Math.random()
    const cr = core[0] + (edge[0] - core[0]) * off * 0.7 + 20 * jitter
    const cg = core[1] + (edge[1] - core[1]) * off * 0.7 + 8 * jitter
    const cb = core[2] + (edge[2] - core[2]) * off * 0.7 - 8 * jitter

    // 亮度：离起点越远越暗、离轴越远越暗
    const life = Math.max(0, Math.min(255, 255 *
      (1 - Math.pow(e, 1.8)) *
      (1 - Math.pow(off, 1.5)) *
      (0.55 + 0.45 * Math.random())))
    if (life < 10) continue

    P.tx[n] = x; P.ty[n] = y
    P.px[n] = x; P.py[n] = y
    P.r[n] = Math.min(255, Math.max(0, cr))
    P.g[n] = Math.min(255, Math.max(0, cg))
    P.b[n] = Math.min(255, Math.max(0, cb))
    P.life[n] = life
    const taper = e < 0.6 ? 1 : 1 - ((e - 0.6) / 0.4) * 0.4
    P.size[n] = (1 + 0.6 * Math.random()) * taper
    P.cursorR[n] = 0.55 + 0.9 * Math.random()
    P.springW[n] = 0.55 + 0.9 * Math.random()
    P.tangent[n] = (Math.random() - 0.5) * 0.3
    n++
  }
  P.count = n
  return P
}


// 预计算姿态（模块级只算一次）
const PLANE_GEO = computePose(PLANE_POSE)
// 开发期自检：机头应为右上（+30°~+60°），若不符会打印告警
if (typeof console !== 'undefined' && noseAngle(PLANE_GEO.vs) < 30) {
  console.warn('[HeroPlane] 机头方向异常：', noseAngle(PLANE_GEO.vs).toFixed(1) + '°，期望 +45°（右上）')
}

/** 画纸飞机到 ctx 原点（薄封装，真正的渲染在 planeGeometry.renderPlane） */
function drawPlane(ctx, size, t) {
  const bob = Math.sin(t * 0.0011) * size * 0.03
  renderPlane(ctx, PLANE_GEO.vs, PLANE_GEO.fitR, size, bob)
}


export default function HeroPlane({ className = '' }) {
  const canvasRef = useRef(null)
  const wrapRef = useRef(null)
  const stateRef = useRef({
    scrollY: 0,
    pointer: { x: -9999, y: -9999, active: false },
    entrance: 1,       // 0→1 入场进度
    entranceStart: 0,
  })

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const cfg = CFG
    const W = cfg.trailWidth
    const H = cfg.trailHeight
    const particleCanvas = document.createElement('canvas')
    particleCanvas.width = W
    particleCanvas.height = H
    const pctx = particleCanvas.getContext('2d')

    let P = buildParticles(cfg.trailParticleCount, W, H, cfg)

    // ---- 尺寸同步（含 DPR，最多 2 倍，避免 4K 屏粒子爆量） ----
    let cssW = 0, cssH = 0, dpr = 1, scale = 1
    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      cssW = wrap.offsetWidth || W
      cssH = wrap.offsetHeight || H
      canvas.width = Math.max(1, Math.floor(cssW * dpr))
      canvas.height = Math.max(1, Math.floor(cssH * dpr))
      canvas.style.width = cssW + 'px'
      canvas.style.height = cssH + 'px'
      // 以短边等比缩放，保证拖尾比例不随窗口变形
      scale = Math.min(cssW / W, cssH / H) * dpr
    }
    resize()

    // ---- 事件：滚动 + 指针 ----
    const onScroll = () => {
      stateRef.current.scrollY = window.scrollY || document.documentElement.scrollTop || 0
    }
    const onPointerMove = (e) => {
      const r = canvas.getBoundingClientRect()
      stateRef.current.pointer.x = e.clientX - r.left
      stateRef.current.pointer.y = e.clientY - r.top
      stateRef.current.pointer.active = true
    }
    const onPointerLeave = () => { stateRef.current.pointer.active = false }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerleave', onPointerLeave)

    let raf = 0
    const start = performance.now()
    // 入场：进入页面立即淡入，0.8s 完成
    //   ⚠️ 原先延迟 1950ms 才开始，导致「刚进页面看不到飞机和粒子、滚动后才出现」的错觉。
    stateRef.current.entranceStart = start

    const frame = (now) => {
      raf = requestAnimationFrame(frame)
      const st = stateRef.current

      // ---- 入场进度 ----
      const ent = Math.min(1, Math.max(0, (now - st.entranceStart) / 800))
      // ease-out
      st.entrance = 1 - Math.pow(1 - ent, 3)
      if (ent <= 0) {
        // 未入场，清屏并等下一帧
        ctx.setTransform(1, 0, 0, 1, 0, 0)
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        return
      }

      // ---- 滚动位置（驱动飞机的飞离动画） ----
      const sy = st.scrollY

      // ================= 3) 纸飞机（先算位置，粒子目标点要用） =================
      // 初始：画布正中；滚动：向右上方飞离 + 缩小 + 淡出
      const t = now - start
      const ex = (1 - st.entrance) * -180
      const ey = (1 - st.entrance) * 90

      const vh = window.innerHeight || 900
      const prog = Math.min(1, Math.max(0, sy / (vh * 0.9)))

      const flyX = prog * 640
      const flyY = prog * -520
      const flyScale = 1 - prog * 0.55
      const flyFade = prog < 0.55 ? 1 : Math.max(0, 1 - (prog - 0.55) / 0.45)

      // 飞机位置（画布坐标）
      const px = W / 2 + cfg.trailOriginOffsetX + 30 + ex + flyX
      const py = H / 2 + cfg.trailOriginOffsetY - 10 + ey + flyY

      // 需求：粒子必须"长"在飞机尾部并随飞机移动。
      // 做法：粒子目标点 = 飞机尾部沿其飞行反方向铺开的一段"尾迹线"，
      //       飞机每帧位置变化时，整条尾迹线一起跟着平移，
      //       粒子再用弹簧+阻尼追上去，就形成始终连着机尾的拖尾。
      const trailTheta = (cfg.trailAngle * Math.PI) / 180
      const tct = Math.cos(trailTheta)
      const tst = Math.sin(trailTheta)
      const trailLen = W * cfg.trailLengthFactor
      const trailSpread = W * cfg.trailSpreadFactor
      // 飞机尾部锚点（机身后方一点）
      const tailX = px - tct * 26
      const tailY = py - tst * 26
      const offX = tailX - (W / 2)
      const offY = tailY - (H / 2)
      if (!P.appliedOffX) { P.appliedOffX = 0; P.appliedOffY = 0 }
      const dOffX = offX - P.appliedOffX
      const dOffY = offY - P.appliedOffY
      P.appliedOffX = offX
      P.appliedOffY = offY

      // ================= 1) 粒子层 =================
      pctx.setTransform(1, 0, 0, 1, 0, 0)
      pctx.clearRect(0, 0, W, H)
      pctx.globalCompositeOperation = 'lighter'

      // 指针在粒子画布坐标系中的位置
      let mx = -9999, my = -9999, mActive = false
      if (st.pointer.active) {
        const cx = cssW / 2, cy = cssH / 2
        mx = (st.pointer.x - cx) / scale + W / 2
        my = (st.pointer.y - cy) / scale + H / 2
        mActive = true
      }

      const D = cfg.trailDamp
      const SP = cfg.trailSpring
      const CR = cfg.trailCursorRadius
      const CF = cfg.trailCursorForce

      const n = P.count
      for (let i = 0; i < n; i++) {
        // 尾迹整体随飞机平移：目标点同步偏移（粒子跟着机尾走的关键）
        if (dOffX !== 0 || dOffY !== 0) {
          P.tx[i] += dOffX
          P.ty[i] += dOffY
        }

        // ⚠️ 注意：这里刻意不做"滚动扰动"。
        // 早期版本让滚动量去推粒子（拖尾被甩开），效果是粒子随滚轮上下乱晃、
        // 与机尾脱节。主人要求粒子紧贴机尾跟随飞行，故滚动只驱动飞机位移，
        // 粒子完全靠"目标点跟随 + 弹簧"贴住尾部。

        // 指针斥力
        if (mActive) {
          const ddx = P.px[i] - mx
          const ddy = P.py[i] - my
          const d2 = ddx * ddx + ddy * ddy
          const rad = CR * P.cursorR[i]
          if (d2 < rad * rad && d2 > 0.01) {
            const d = Math.sqrt(d2)
            const fall = 1 - d / rad
            const ff = CF * fall * fall * 0.05 * P.springW[i]
            const nx = ddx / d
            const ny = ddy / d
            P.vx[i] += (ddx / d + ny * P.tangent[i]) * ff
            P.vy[i] += (ddy / d - nx * P.tangent[i]) * ff
          }
        }

        // 阻尼 + 位置积分 + 弹簧追向移动中的目标点
        P.vx[i] *= D
        P.vy[i] *= D
        P.px[i] += P.vx[i]
        P.py[i] += P.vy[i]
        P.px[i] += (P.tx[i] - P.px[i]) * SP
        P.py[i] += (P.ty[i] - P.py[i]) * SP

        // 绘制
        const life = P.life[i]
        if (life < 8) continue
        const rad = 0.5 * P.size[i] * cfg.trailParticleSize
        const alpha = (life / 255) * st.entrance
        pctx.fillStyle = `rgba(${P.r[i]},${P.g[i]},${P.b[i]},${alpha})`
        pctx.beginPath()
        pctx.arc(P.px[i], P.py[i], rad, 0, Math.PI * 2)
        pctx.fill()
      }

      // ================= 2) 合成到主画布 =================
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const ox = (canvas.width - W * scale) / 2
      const oy = (canvas.height - H * scale) / 2
      ctx.setTransform(scale, 0, 0, scale, ox, oy)
      ctx.drawImage(particleCanvas, 0, 0)

      // ================= 4) 画纸飞机 =================
      ctx.save()
      ctx.globalAlpha = st.entrance * flyFade
      ctx.translate(px, py)
      const planeRot = prog * 18 + Math.sin(t * 0.0007) * 1.5
      ctx.rotate((-planeRot * Math.PI) / 180)
      const ps = flyScale
      ctx.scale(ps, ps)
      drawPlane(ctx, cfg.planeDisplaySize, t)
      ctx.restore()

      ctx.setTransform(1, 0, 0, 1, 0, 0)
    }

    raf = requestAnimationFrame(frame)

    const ro = new ResizeObserver(resize)
    ro.observe(wrap)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerleave', onPointerLeave)
    }
  }, [])

  return (
    <div
      ref={wrapRef}
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      aria-hidden="true"
    >
      <canvas ref={canvasRef} className="block h-full w-full" />
    </div>
  )
}
