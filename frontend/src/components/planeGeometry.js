/**
 * 纸飞机 3D 姿态 —— 唯一渲染源（single source of truth）
 *
 * ⚠️ 为什么要有这个文件：
 *   plane-preview.html（调参页）与 HeroPlane.jsx（网页）必须用【同一套】姿态计算，
 *   否则会出现「预览页调好了、搬到网页里就变样」。历史上就是因为两边各写一份，
 *   参数越调越乱。现在两边共用本模块，预览页所见 = 网页所得。
 *
 * 模型坐标系（原始 mesh）：+Z = 机身纵轴（-3.5 端是机头尖点，+1.5 端是机尾宽面）
 * 屏幕坐标系：x 向右，y 向下
 */

/* 纸飞机 3D 网格：从 trajectory.ai 的 WebGL 版本提取（43 顶点 / 20 三角形） */
export const PLANE_IDX = [42,38,37,41,36,34,38,33,31,40,30,28,25,27,24,39,25,23,38,31,37,36,35,34,33,32,31,30,29,28,27,26,24,25,24,23,22,11,21,20,10,19,18,9,17,8,7,6,5,16,13,4,15,14,3,13,12,1,2,0]

export const PLANE_POS = [
  [0,1.2076,-3.5], [0,-0.1797,1.5], [-0.6631,1.2076,1.5], [-1.9894,1.2076,1.5],
  [0.6631,1.2076,1.5], [1.9894,1.2076,1.5], [0,1.2474,-3.4963], [0,-0.1411,1.5107],
  [-0.6403,1.2403,1.503], [-1.9894,1.2476,1.5], [0.6403,1.2403,1.503], [1.9894,1.2476,1.5],
  [-0.6631,1.2076,1.5], [0,1.2076,-3.5], [0,1.2076,-3.5], [0,-0.1797,1.5],
  [0.6631,1.2076,1.5], [-0.6403,1.2403,1.503], [0,1.2474,-3.4963], [0,1.2474,-3.4963],
  [0,-0.1411,1.5107], [0,1.2474,-3.4963], [0.6403,1.2403,1.503], [0,-0.1797,1.5],
  [-0.6631,1.2076,1.5], [-0.6403,1.2403,1.503], [-1.9894,1.2076,1.5], [-1.9894,1.2476,1.5],
  [-1.9894,1.2076,1.5], [0,1.2076,-3.5], [0,1.2474,-3.4963], [0.6631,1.2076,1.5],
  [0,-0.1797,1.5], [0,-0.1411,1.5107], [0,1.2076,-3.5], [1.9894,1.2076,1.5],
  [1.9894,1.2476,1.5], [1.9894,1.2076,1.5], [0.6403,1.2403,1.503], [0,-0.1411,1.5107],
  [-1.9894,1.2476,1.5], [0,1.2474,-3.4963], [1.9894,1.2476,1.5],
]

/* ---- 向量工具 ---- */
export function vRotX(v, a) { const c=Math.cos(a), s=Math.sin(a); return [v[0], v[1]*c-v[2]*s, v[1]*s+v[2]*c] }
export function vRotY(v, a) { const c=Math.cos(a), s=Math.sin(a); return [v[0]*c+v[2]*s, v[1], -v[0]*s+v[2]*c] }
export function vRotZ(v, a) { const c=Math.cos(a), s=Math.sin(a); return [v[0]*c-v[1]*s, v[0]*s+v[1]*c, v[2]] }
export function vNorm(v) { const L = Math.hypot(v[0],v[1],v[2]) || 1; return [v[0]/L, v[1]/L, v[2]/L] }
export const deg = (d) => (d * Math.PI) / 180

/* ---- 姿态参数（唯一来源）----
 * 由主人用 plane-preview.html 拖动确认。
 * 预览页与网页共用本模块，因此「预览所见 = 网页所得」（已用顶点比对验证差异为 0）。
 */
export const PLANE_POSE = {
  rot90: 90,     // 模型绕 Y 轴转正
  yaw: 135,      // 水平转向
  pitch: 90,     // 俯仰
  roll: -20,     // 侧倾
  // 主人调参页微调值（Z 滑块基准 20，故 extraZ = 131 - 20）
  extraZ: 111,
  extraY: 6,
  extraX: 90,
}

/* ---- 相机 ---- */
export const PLANE_CAM = { camDist: 6.5, persp: 0.30 }

/* ---- 光照与配色（对齐原站参考图）---- */
export const PLANE_LIGHT = vNorm([0.55, 0.8, 0.45])
export const PLANE_TAIL  = [0xEC, 0xD5, 0xE4]   // 尾部：淡粉紫
export const PLANE_MID   = [0xF7, 0xE6, 0xE8]   // 中段：淡粉
export const PLANE_NOSE  = [0xFD, 0xF4, 0xF0]   // 机头：接近白
export const PLANE_RIM   = [0x8A, 0x6C, 0xB8]   // 边缘光：紫
export const PLANE_SHADE = [0xC9, 0xA8, 0xC4]   // 背光面：粉紫阴影

/** 机头 / 机尾顶点下标（模型原始 Z 轴：-3.5 端是尖的机头，+1.5 端是宽的机尾） */
export const HEAD_I = PLANE_POS.findIndex((p) => p[2] === Math.min(...PLANE_POS.map(q => q[2])))
export const TAIL_I = PLANE_POS.findIndex((p) => p[2] === Math.max(...PLANE_POS.map(q => q[2])))

/**
 * 计算姿态变换后的顶点（含居中 + 归一化）。
 * @param {{rot90:number,yaw:number,pitch:number,roll:number,extraZ?:number,extraY?:number,extraX?:number}} pose
 * @returns {{vs:number[][], fitR:number}}
 */
export function computePose(pose = PLANE_POSE) {
  const { rot90, yaw, pitch, roll, extraZ = 0, extraY = 0, extraX = 0 } = pose
  let vs = PLANE_POS.map((p) => vRotY(p, deg(rot90)))
  const cx = vs.reduce((s, p) => s + p[0], 0) / vs.length
  const cy = vs.reduce((s, p) => s + p[1], 0) / vs.length
  const cz = vs.reduce((s, p) => s + p[2], 0) / vs.length
  vs = vs.map((p) => [p[0] - cx, p[1] - cy, p[2] - cz])
  // 基准姿态：roll → yaw → pitch
  vs = vs.map((p) => vRotX(vRotY(vRotZ(p, deg(roll)), deg(yaw)), deg(pitch)))
  // 叠加微调：Z → Y → X
  if (extraZ) vs = vs.map((p) => vRotZ(p, deg(extraZ)))
  if (extraY) vs = vs.map((p) => vRotY(p, deg(extraY)))
  if (extraX) vs = vs.map((p) => vRotX(p, deg(extraX)))
  const maxr = Math.max(...vs.map((p) => Math.hypot(p[0], p[1], p[2]))) || 1
  vs = vs.map((p) => p.map((v) => v / maxr))
  const fitR = Math.max(...vs.map((p) => Math.hypot(p[0], p[1]))) || 1
  return { vs, fitR }
}

/** 机头相对机尾的屏幕方向角（度，0=右 90=上 ±180=左 -90=下）*/
export function noseAngle(vs) {
  const h = vs[HEAD_I], t = vs[TAIL_I]
  return (Math.atan2(-(h[1] - t[1]), h[0] - t[0]) * 180) / Math.PI
}

/**
 * 把飞机姿态渲染到 ctx 原点（ctx 已 translate 到飞机中心）。
 * 透视投影 + 双面平面着色 + 机身渐变 + Fresnel 边缘光。
 * @param {CanvasRenderingContext2D} ctx
 * @param {number[][]} vs       computePose 返回的顶点
 * @param {number} fitR         computePose 返回的屏幕半径
 * @param {number} size         屏幕上飞机的目标直径(px)
 * @param {number} bob          竖向浮动偏移(px)
 */
export function renderPlane(ctx, vs, fitR, size, bob = 0) {
  const rad2 = (size * 0.5) / fitR
  const { camDist, persp } = PLANE_CAM
  const proj = (p) => {
    const zc = Math.max(p[2] * persp + camDist, 0.1) / camDist
    return [(p[0] * rad2) / zc, (p[1] * rad2) / zc]
  }

  const tris = []
  for (let k = 0; k < PLANE_IDX.length; k += 3) {
    const a = PLANE_IDX[k], b = PLANE_IDX[k+1], c = PLANE_IDX[k+2]
    const pa = proj(vs[a]), pb = proj(vs[b]), pc = proj(vs[c])
    const e1 = [vs[b][0]-vs[a][0], vs[b][1]-vs[a][1], vs[b][2]-vs[a][2]]
    const e2 = [vs[c][0]-vs[a][0], vs[c][1]-vs[a][1], vs[c][2]-vs[a][2]]
    let fn = vNorm([
      e1[1]*e2[2]-e1[2]*e2[1],
      e1[2]*e2[0]-e1[0]*e2[2],
      e1[0]*e2[1]-e1[1]*e2[0],
    ])
    if (fn[2] > 0) fn = [-fn[0], -fn[1], -fn[2]]   // 双面光照
    tris.push({
      z: (vs[a][2] + vs[b][2] + vs[c][2]) / 3,
      pts: [pa, pb, pc],
      fn,
      gx: (vs[a][0] + vs[b][0] + vs[c][0]) / 3,
    })
  }
  tris.sort((u, v) => v.z - u.z)   // 远 → 近（画家算法）

  ctx.save()
  ctx.translate(0, bob)
  for (const t of tris) {
    const d = t.fn[0]*PLANE_LIGHT[0] + t.fn[1]*PLANE_LIGHT[1] + t.fn[2]*PLANE_LIGHT[2]
    const diffuse = Math.max(d, 0) + Math.max(-d, 0) * 0.30
    // 机身纵向渐变：尾部(粉紫) → 中段(淡粉) → 机头(近白)
    const g = Math.max(0, Math.min(1, (t.gx + 1) / 2))
    const mix = (A, B, k) => [0,1,2].map((i) => A[i] + (B[i] - A[i]) * k)
    const base = g < 0.5 ? mix(PLANE_TAIL, PLANE_MID, g * 2) : mix(PLANE_MID, PLANE_NOSE, (g - 0.5) * 2)
    const shade = 0.55 + 0.62 * diffuse
    const amb = 1 - Math.min(1, diffuse * 1.35)
    const fres = Math.pow(1 - Math.abs(d), 3) * 0.22
    const col = [0,1,2].map((i) =>
      Math.max(0, Math.min(255, Math.round(
        base[i] * shade + PLANE_SHADE[i] * amb * 0.34 + PLANE_RIM[i] * fres
      )))
    )
    ctx.fillStyle = `rgb(${col[0]},${col[1]},${col[2]})`
    ctx.beginPath()
    ctx.moveTo(t.pts[0][0], t.pts[0][1])
    ctx.lineTo(t.pts[1][0], t.pts[1][1])
    ctx.lineTo(t.pts[2][0], t.pts[2][1])
    ctx.closePath()
    ctx.fill()
  }
  ctx.restore()
}
