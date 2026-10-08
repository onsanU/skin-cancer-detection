/**
 * 可解释性分析面板 —— Grad-CAM 热力图 + 配套量化图表
 * ================================================================
 * 参考 DUNEScan / SHAMSul 的信息组织方式：
 *   ① 热力图图集       —— 原图 vs 各模型关注区域
 *   ② 归属集中度柱状图 —— 各模型高关注区占比
 *   ③ 概率对比柱状图   —— 各成员模型独立给出的恶性概率
 *   ④ 空间一致性矩阵   —— 模型两两之间热力图的相关性
 *   ⑤ 特征空间散点图   —— 当前图像在验证集特征空间中的落点
 * 每个区块配「这是什么意思？」折叠说明（默认收起，避免信息过载）
 */
import { useEffect, useMemo, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ScatterChart, Scatter, ZAxis, ReferenceLine,
} from 'recharts'

/* ---------- 通用：折叠说明 ---------- */
function Hint({ title = '这是什么意思？', text, children }) {
  const [open, setOpen] = useState(false)
  if (!text && !children) return null
  return (
    <div className="mt-3 border-t border-slate-100 pt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-medical-600 hover:text-medical-700 flex items-center gap-1 transition"
      >
        <span className={`transition-transform ${open ? 'rotate-90' : ''}`}>▶</span>
        {title}
      </button>
      {open && (
        <div className="mt-2 text-xs text-slate-500 leading-relaxed bg-slate-50 rounded-lg px-3 py-2">
          {text}
          {children}
        </div>
      )}
    </div>
  )
}

/* ---------- 通用：区块标题 ---------- */
function SectionTitle({ icon, title, badge }) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <h3 className="font-semibold text-slate-800">{icon} {title}</h3>
      {badge}
    </div>
  )
}

/* ---------- 色带图例 ---------- */
function ColorLegend({ legend }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-slate-500">
      <span>{legend?.low || '低关注'}</span>
      <div
        className="h-2.5 w-24 rounded-full"
        style={{
          background:
            'linear-gradient(90deg,#ebf5fc 0%,#a5cdf0 25%,#469cdc 50%,#1469be 72%,#faaf3c 88%,#e65537 100%)',
        }}
      />
      <span>{legend?.high || '高关注'}</span>
    </div>
  )
}

/* ================================================================
 *  主组件（默认导出：右栏部分 —— 一致性矩阵 + 特征空间）
 *  左栏部分用命名导出 ExplainLeft
 * ================================================================ */
export default function ExplainPanel({ gradcam, explanation }) {
  const [surfaceBase, setSurfaceBase] = useState(null)
  const [surfaceErr, setSurfaceErr] = useState('')

  const hasSurface = !!explanation?.feature_surface

  // 按需拉取特征空间底图（只在需要时请求，避免无谓流量）
  useEffect(() => {
    if (!hasSurface || surfaceBase) return
    fetch('/api/explain/feature-surface')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('底图数据未就绪'))))
      .then(setSurfaceBase)
      .catch((e) => setSurfaceErr(e.message))
  }, [hasSurface, surfaceBase])

  if (!gradcam?.images?.length) return null

  const agree = explanation?.agreement
  const surface = explanation?.feature_surface

  return (
    <div className="space-y-4">
      {agree?.matrix?.length > 0 && (
        <ChartCard icon="🔗" title="模型间空间一致性" hint={agree.explain}>
          <AgreementMatrix matrix={agree.matrix} members={agree.members} />
          <p className="text-xs text-slate-500 mt-3 leading-relaxed">{agree.text}</p>
        </ChartCard>
      )}

      {surface && (
        <ChartCard
          icon="🗺️"
          title="特征空间位置"
          hint={surface.explain}
          badge={
            surface.meta && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                {surface.meta.method} · {surface.meta.n_samples} 参考样本
              </span>
            )
          }
        >
          {surfaceBase ? (
            <SurfaceChart base={surfaceBase} point={surface} />
          ) : (
            <div className="h-56 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg">
              {surfaceErr || '正在加载特征空间底图…'}
            </div>
          )}
          <p className="text-xs text-slate-500 mt-3 leading-relaxed">{surface.text}</p>
          {surface.meta && (
            <p className="text-[11px] text-slate-400 mt-2">
              底图：{surface.meta.source}（良性 {surface.meta.n_benign} / 恶性 {surface.meta.n_malignant}）
            </p>
          )}
        </ChartCard>
      )}
    </div>
  )
}

/* ================================================================
 *  左栏部分：热力图 + 概率对比 + 注意力集中度
 *  （放在「检测参数」下方，与右栏结果区高度对齐）
 * ================================================================ */
export function ExplainLeft({ gradcam, explanation }) {
  if (!gradcam?.images?.length) return null

  const images = gradcam.images || []
  const conc = explanation?.concentration
  const probs = explanation?.probabilities

  return (
    <div className="space-y-4">
      {/* 热力图 */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <SectionTitle
          icon="🔥"
          title="模型关注区域"
          badge={
            <span className="text-xs px-2 py-0.5 rounded-full bg-medical-50 text-medical-700 font-medium">
              {gradcam.method || 'Grad-CAM'}
            </span>
          }
        />
        <p className="text-xs text-slate-500 mb-4">
          热力图显示模型在做判断时最关注图像中的哪些区域。颜色越暖表示关注度越高。
        </p>

        <div className={`grid gap-3 ${images.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}>
          {images.map((im, i) => (
            <figure key={im.member || i} className="rounded-lg overflow-hidden border border-slate-200">
              <div className="bg-slate-900">
                <img
                  src={im.url}
                  alt={`${im.member} 热力图`}
                  loading="lazy"
                  className="w-full block"
                />
              </div>
              <figcaption className="px-3 py-2 bg-slate-50 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-600 font-medium truncate" title={im.member}>
                    {im.member}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-full font-medium shrink-0 ${
                      im.focus === 'malignant'
                        ? 'bg-danger-50 text-danger-600'
                        : 'bg-safe-50 text-safe-600'
                    }`}
                  >
                    {im.focus_cn} {(Math.max(im.malignant_prob, im.benign_prob) * 100).toFixed(1)}%
                  </span>
                </div>
                {gradcam.target_layer?.[im.member] && (
                  <div className="text-[10px] text-slate-400 mt-0.5 font-mono">
                    目标层 {gradcam.target_layer[im.member]}
                  </div>
                )}
              </figcaption>
            </figure>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <ColorLegend legend={gradcam.legend} />
          {gradcam.elapsed_ms != null && (
            <span className="text-[11px] text-slate-400 font-mono">
              耗时 {gradcam.elapsed_ms.toFixed(0)}ms
            </span>
          )}
        </div>

        <Hint text={gradcam.legend?.note}>
          {gradcam.disclaimer && (
            <div className="mt-2 text-slate-400 leading-relaxed">{gradcam.disclaimer}</div>
          )}
        </Hint>
      </div>

      {/* 各成员模型判定 */}
      {probs?.items?.length > 0 && (
        <ChartCard icon="📊" title="各成员模型判定" hint={probs.explain}>
          <ProbabilityChart items={probs.items} ensemble={probs.ensemble_malignant} />
          <p className="text-xs text-slate-500 mt-3 leading-relaxed">{probs.text}</p>
          <ThresholdMarks threshold={explanation?.threshold} />
        </ChartCard>
      )}

      {/* 注意力集中度 */}
      {conc?.items?.length > 0 && (
        <ChartCard icon="🎯" title="注意力集中度" hint={conc.explain}>
          <ConcentrationChart items={conc.items} />
          <p className="text-xs text-slate-500 mt-3 leading-relaxed">{conc.text}</p>
        </ChartCard>
      )}
    </div>
  )
}

/* ================================================================
 *  子组件
 * ================================================================ */
function ChartCard({ icon, title, hint, badge, children }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <SectionTitle icon={icon} title={title} badge={badge} />
      {children}
      <Hint text={hint} />
    </div>
  )
}

/* ---------- 概率对比柱状图 ---------- */
function ProbabilityChart({ items, ensemble }) {
  const rows = [
    ...items.map((it) => ({
      name: shorten(it.member),
      恶性: +(it.malignant_prob * 100).toFixed(1),
      良性: +(it.benign_prob * 100).toFixed(1),
    })),
    { name: '集成结果', 恶性: +((ensemble || 0) * 100).toFixed(1), 良性: +((1 - (ensemble || 0)) * 100).toFixed(1), isEnsemble: true },
  ]
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} interval={0} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#94a3b8' }} unit="%" />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
            formatter={(v) => `${v}%`}
          />
          <Bar dataKey="恶性" fill="#ef4444" radius={[3, 3, 0, 0]} maxBarSize={38} />
          <Bar dataKey="良性" fill="#10b981" radius={[3, 3, 0, 0]} maxBarSize={38} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---------- 阈值标注（在概率图下方画一条刻度轴）---------- */
function ThresholdMarks({ threshold }) {
  const marks = [
    { label: '筛查', v: 0.20 },
    { label: '平衡', v: 0.33 },
    { label: '精确', v: 0.48 },
  ]
  if (!threshold) return null
  const pct = Math.min(100, Math.max(0, threshold * 100))
  return (
    <div className="mt-3">
      <div className="text-[11px] text-slate-500 mb-1.5">
        当前判定阈值 <b className="font-mono text-medical-700">{threshold.toFixed(2)}</b>
        <span className="text-slate-400 ml-1">（恶性概率 ≥ 此值判为恶性）</span>
      </div>
      <div className="relative h-7">
        <div className="absolute top-1.5 left-0 right-0 h-1.5 rounded-full bg-gradient-to-r from-safe-400 via-amber-300 to-danger-400" />
        {marks.map((m) => (
          <div
            key={m.label}
            className="absolute top-0 -translate-x-1/2 flex flex-col items-center"
            style={{ left: `${m.v * 100}%` }}
          >
            <div className="w-px h-3.5 bg-white/70" />
            <span className="text-[10px] text-slate-400 whitespace-nowrap mt-0.5">{m.label}</span>
          </div>
        ))}
        <div
          className="absolute top-0 -translate-x-1/2 flex flex-col items-center"
          style={{ left: `${pct}%` }}
        >
          <div className="w-0.5 h-4 bg-slate-800 rounded-full" />
          <span className="text-[10px] font-semibold text-slate-700 whitespace-nowrap mt-0.5">
            当前
          </span>
        </div>
      </div>
    </div>
  )
}

/* ---------- 集中度柱状图 ---------- */
function ConcentrationChart({ items }) {
  const data = items.map((it) => ({
    name: shorten(it.member || `模型${items.indexOf(it) + 1}`),
    pct: it.pct,
  }))
  // 用颜色深浅表达集中程度
  const color = (v) => (v >= 20 ? '#1469be' : v >= 10 ? '#469cdc' : v >= 4 ? '#a5cdf0' : '#dbeafe')
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} interval={0} />
          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} unit="%" />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
            formatter={(v) => [`${v}%`, '高关注区占比']}
          />
          <Bar dataKey="pct" radius={[3, 3, 0, 0]} maxBarSize={54}>
            {data.map((d, i) => (
              <Cell key={i} fill={color(d.pct)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---------- 一致性矩阵 ---------- */
function AgreementMatrix({ matrix, members }) {
  const short = members.map(shorten)
  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-separate border-spacing-1">
        <thead>
          <tr>
            <th className="w-20" />
            {short.map((m, i) => (
              <th key={i} className="font-medium text-slate-500 px-1 pb-1 text-center">{m}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={i}>
              <td className="font-medium text-slate-500 pr-2 text-right whitespace-nowrap">{short[i]}</td>
              {row.map((v, j) => {
                const isDiag = i === j
                // 相关系数 -1~1 → 蓝白红
                const bg = isDiag
                  ? '#1e293b'
                  : v >= 0
                    ? `rgba(20,105,190,${0.12 + Math.min(v, 1) * 0.78})`
                    : `rgba(239,68,68,${0.12 + Math.min(-v, 1) * 0.78})`
                const fg = isDiag || Math.abs(v) > 0.5 ? '#fff' : '#334155'
                return (
                  <td
                    key={j}
                    className="w-20 h-14 text-center font-mono font-semibold rounded-md transition"
                    style={{ background: bg, color: fg }}
                    title={isDiag ? '自身' : `${short[i]} ↔ ${short[j]} 相关系数 ${v}`}
                  >
                    {v.toFixed(2)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-slate-500 border-t border-slate-100 pt-2.5">
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-4 rounded shrink-0" style={{ background: '#1469be' }} /> 高度一致
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-4 rounded shrink-0" style={{ background: 'rgba(20,105,190,0.25)' }} /> 部分一致
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-4 rounded shrink-0" style={{ background: 'rgba(239,68,68,0.5)' }} /> 负相关
        </span>
        <span className="text-slate-400 whitespace-nowrap">对角线为自身，恒为 1.00</span>
      </div>
    </div>
  )
}

/* ---------- 特征空间散点图 ---------- */
function SurfaceChart({ base, point }) {
  const pts = base?.points || []
  const benign = useMemo(() => pts.filter((p) => p.label === 'benign'), [pts])
  const malignant = useMemo(() => pts.filter((p) => p.label === 'malignant'), [pts])

  if (!pts.length) {
    return (
      <div className="h-64 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg">
        底图数据为空
      </div>
    )
  }

  const current = [{ x: point.x, y: point.y, name: '当前图像' }]

  return (
    <div className="flex flex-col">
      {/* 图表区：固定高度，独立占位，不挤压下方图例 */}
      <div className="h-80 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 14, left: -14, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              type="number" dataKey="x" name="维度1"
              domain={[-1.1, 1.1]} tick={{ fontSize: 10, fill: '#94a3b8' }}
            />
            <YAxis
              type="number" dataKey="y" name="维度2"
              domain={[-1.1, 1.1]} tick={{ fontSize: 10, fill: '#94a3b8' }}
            />
            <ZAxis range={[28, 28]} />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
              formatter={(v, n, p) => {
                const d = p?.payload
                if (!d) return [v, n]
                if (d.name === '当前图像') return ['当前图像', '']
                return [`${d.name}（${d.label === 'malignant' ? '恶性' : '良性'}）`,
                        `模型恶性概率 ${(d.prob * 100).toFixed(1)}%`]
              }}
            />
            <Scatter name="良性样本" data={benign} fill="#10b981" fillOpacity={0.55} />
            <Scatter name="恶性样本" data={malignant} fill="#ef4444" fillOpacity={0.55} />
            <Scatter name="当前图像" data={current} fill="#0f172a" shape="circle" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      {/* 图例：与图表区分离，独占一行 */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 text-[11px] text-slate-500 border-t border-slate-100 pt-2.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-safe-500 shrink-0" />验证集良性
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-danger-500 shrink-0" />验证集恶性
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-slate-900 ring-2 ring-white shadow shrink-0" />当前图像
          </span>
        </div>
        <span className="font-mono text-slate-400 whitespace-nowrap">
          坐标 ({point.x.toFixed(2)}, {point.y.toFixed(2)})
        </span>
      </div>
    </div>
  )
}

/* ---------- 工具 ---------- */
function shorten(name, max = 12) {
  if (!name) return ''
  // models_vE_r101_288 → r101_288
  const s = name.replace(/^models_/, '')
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}
