import { useCallback, useEffect, useRef, useState } from 'react'
import { predictApi, api } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { Link } from 'react-router-dom'
import ExplainPanel, { ExplainLeft } from '../components/ExplainPanel'

const MAX_MB = 10

// 阈值预设（若后端不可用则用这份兜底）
const LOCATION_OPTIONS = [
  { key: 'face', label: '面部 / 耳 / 鼻' },
  { key: 'scalp', label: '头皮 / 颈部' },
  { key: 'trunk', label: '躯干 / 胸 / 腹 / 背' },
  { key: 'arm', label: '上肢 / 手' },
  { key: 'leg', label: '下肢 / 足' },
  { key: 'genital', label: '生殖器部位' },
  { key: 'unknown', label: '不便说明' },
]

const FALLBACK_PRESETS = {
  screening: { name: '筛查模式', value: 0.32, desc: '优先不漏诊，恶性召回 95.8%，漏诊率 4.2%' },
  balanced: { name: '平衡模式', value: 0.5, desc: '准确率与召回兼顾，准确率 85.0%，恶性召回 89.0%' },
  accurate: { name: '精确模式', value: 0.51, desc: '约登指数最优，适合作为确诊参考' },
}

export default function DetectPage() {
  const { user } = useAuth()
  const fileRef = useRef(null)

  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [location, setLocation] = useState('')
  const [presets, setPresets] = useState(FALLBACK_PRESETS)
  const [mode, setMode] = useState('balanced')
  const [threshold, setThreshold] = useState(FALLBACK_PRESETS.balanced.value)

  // 拉取后端预设
  useEffect(() => {
    api
      .get('/thresholds')
      .then((r) => {
        if (r.data?.presets) {
          setPresets(r.data.presets)
          // 用后端真实阈值对齐当前模式（避免前后端默认值不一致）
          setMode((m) => {
            const v = r.data.presets[m]?.value
            if (v != null) setThreshold(v)
            return m
          })
        }
      })
      .catch(() => {})
  }, [])



  const pickMode = (key) => {
    setMode(key)
    const v = presets[key]?.value
    if (v != null) setThreshold(v)
  }

  // 手动微调：若偏离所选模式的阈值，则标记为「自定义」，避免模式高亮与实际阈值不一致
  const onSlidingThreshold = (v) => {
    setThreshold(v)
    const presetVal = presets[mode]?.value
    if (presetVal != null && Math.abs(v - presetVal) > 0.0001) setMode('custom')
  }

  const pickFile = useCallback((f) => {
    setError('')
    setResult(null)
    if (!f) return
    if (!/^image\/(jpeg|png|bmp|webp)$/.test(f.type)) {
      setError('请选择 JPG / PNG / BMP / WEBP 格式的图片')
      return
    }
    if (f.size / 1024 / 1024 > MAX_MB) {
      setError(`图片不能超过 ${MAX_MB}MB（当前 ${(f.size / 1024 / 1024).toFixed(1)}MB）`)
      return
    }
    setFile(f)
    setPreview(URL.createObjectURL(f))
  }, [])

  const onDrop = useCallback(
    (e) => {
      e.preventDefault()
      setDragging(false)
      pickFile(e.dataTransfer.files?.[0])
    },
    [pickFile]
  )

  const runDetect = async () => {
    if (!file) return
    setLoading(true)
    setError('')
    setProgress(0)
    setResult(null)
    try {
      const data = await predictApi.detect(file, {
        threshold,
        note,
        location: location || undefined,
        onProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 100))
        },
      })
      setResult(data)
    } catch (e) {
      setError(e.message || '检测失败，请稍后重试')
    } finally {
      setLoading(false)
      setProgress(0)
    }
  }

  const reset = () => {
    setFile(null)
    setPreview('')
    setResult(null)
    setError('')
    setNote('')
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">皮肤病变图像检测</h1>
        <p className="text-sm text-slate-500 mt-1">
          上传皮肤病变部位的图像，系统将自动分析并给出良恶性倾向判断
        </p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* ============ 左：上传区 ============ */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h2 className="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-medical-100 text-medical-700 text-xs flex items-center justify-center font-bold">
                1
              </span>
              上传图像
            </h2>

            {!preview ? (
              <div
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => fileRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition ${
                  dragging
                    ? 'drop-active border-medical-400'
                    : 'border-slate-300 hover:border-medical-400 hover:bg-slate-50'
                }`}
              >
                <div className="text-5xl mb-3">📷</div>
                <p className="text-slate-700 font-medium">
                  拖拽图像到此处，或点击选择文件
                </p>
                <p className="text-xs text-slate-400 mt-2">
                  支持 JPG / PNG / BMP / WEBP，单个文件不超过 {MAX_MB}MB
                </p>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/bmp,image/webp"
                  className="hidden"
                  onChange={(e) => pickFile(e.target.files?.[0])}
                />
              </div>
            ) : (
              <div className="space-y-3">
                <div className="relative rounded-xl overflow-hidden bg-slate-900">
                  <img
                    src={preview}
                    alt="预览"
                    className="w-full max-h-80 object-contain"
                  />
                  {loading && <div className="scan-line" />}
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500 truncate max-w-[60%]">
                    {file.name}
                  </span>
                  <span className="text-slate-400">
                    {(file.size / 1024).toFixed(0)} KB
                  </span>
                </div>
              </div>
            )}

            {error && (
              <div className="mt-3 text-sm text-danger-600 bg-danger-50 border border-danger-200 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
          </div>

          {/* 参数 */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h2 className="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-medical-100 text-medical-700 text-xs flex items-center justify-center font-bold">
                2
              </span>
              检测参数
            </h2>

            <label className="block text-sm text-slate-600 mb-2">
              工作模式
              <span className="text-xs text-slate-400 ml-2">
                （不同模式对应不同判定阈值）
              </span>
            </label>
            <div className="grid grid-cols-3 gap-2 mb-4">
              {Object.entries(presets).map(([key, p]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => pickMode(key)}
                  className={`px-3 py-2 rounded-lg text-xs font-medium border transition text-center ${
                    mode === key
                      ? 'bg-medical-50 border-medical-500 text-medical-700 shadow-sm'
                      : 'bg-white border-slate-200 text-slate-600 hover:border-medical-300'
                  }`}
                >
                  <div className="font-semibold">{p.name}</div>
                  <div className="text-[10px] opacity-70 mt-0.5">
                    阈值 {p.value}
                  </div>
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2 mb-4">
              {mode === 'custom' ? (
                <span className="text-medical-700">
                  自定义阈值 {threshold.toFixed(2)}（未对应预设模式，可点击上方按钮恢复预设）
                </span>
              ) : (
                presets[mode]?.desc
              )}
            </p>

            <label className="block text-sm text-slate-600 mb-2">
              手动微调阈值：
              <span className="font-mono font-semibold text-medical-700">
                {threshold.toFixed(2)}
              </span>
              {mode === 'custom' && (
                <span className="text-[10px] ml-2 px-1.5 py-0.5 rounded bg-medical-100 text-medical-700 align-middle">
                  自定义
                </span>
              )}
              <span className="text-xs text-slate-400 ml-2">
                （越低越敏感，漏诊更少但误报更多）
              </span>
            </label>
            <input
              type="range"
              min="0.20"
              max="0.80"
              step="0.01"
              value={threshold}
              onChange={(e) => onSlidingThreshold(parseFloat(e.target.value))}
              className="w-full accent-medical-600"
            />
            <div className="flex justify-between text-xs text-slate-400 mt-1">
              <span>0.20 高敏感</span>
              <span>0.50</span>
              <span>0.80 高特异</span>
            </div>

            <label className="block text-sm text-slate-600 mt-4 mb-1">
              病变部位（可选，用于展示该部位常见病变参考）
            </label>
            <select
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-medical-500 focus:border-transparent"
            >
              <option value="">不指定</option>
              {LOCATION_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>{o.label}</option>
              ))}
            </select>

            <label className="block text-sm text-slate-600 mt-4 mb-1">
              备注（可选）
            </label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="如：手臂内侧，发现2周"
              className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-medical-500 focus:border-transparent"
            />


            <div className="flex gap-3 mt-5">
              <button
                onClick={runDetect}
                disabled={!file || loading}
                className="flex-1 py-2.5 rounded-lg bg-medical-600 text-white font-medium hover:bg-medical-700 disabled:opacity-40 disabled:cursor-not-allowed transition shadow-sm"
              >
                {loading
                  ? progress > 0 && progress < 100
                    ? `上传中 ${progress}%`
                    : '分析中...'
                  : '开始检测'}
              </button>
              <button
                onClick={reset}
                disabled={loading}
                className="px-4 py-2.5 rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition"
              >
                重置
              </button>
            </div>

            {!user && (
              <p className="text-xs text-slate-400 mt-3">
                💡 当前为游客模式，检测记录不会保存。
                <Link to="/login" className="text-medical-600 hover:underline">
                  登录
                </Link>
                后可保留历史记录。
              </p>
            )}
          </div>

          {/* ============ 模型解释（左半部分）：检测完成后出现 ============ */}
          {result?.gradcam?.images?.length > 0 && (
            <>
              <div className="flex items-center gap-3 pt-1">
                <div className="h-px flex-1 bg-slate-200" />
                <span className="text-xs font-medium text-slate-400 whitespace-nowrap">
                  🔬 模型解释
                </span>
                <div className="h-px flex-1 bg-slate-200" />
              </div>
              <ExplainLeft gradcam={result.gradcam} explanation={result.explanation} />
            </>
          )}
        </div>

        {/* ============ 右：结果区 ============ */}
        <div>
          {!result && !loading && (
            <div className="bg-white rounded-xl border border-slate-200 p-10 shadow-sm h-full flex flex-col items-center justify-center text-center">
              <div className="text-6xl mb-4 opacity-30">🔬</div>
              <p className="text-slate-400">检测结果将在这里显示</p>
            </div>
          )}

          {loading && (
            <div className="bg-white rounded-xl border border-slate-200 p-10 shadow-sm h-full flex flex-col items-center justify-center">
              <div className="w-12 h-12 border-4 border-medical-200 border-t-medical-600 rounded-full animate-spin mb-4" />
              <p className="text-slate-600">正在分析图像...</p>
              <p className="text-xs text-slate-400 mt-1">
                模型推理 + 特征提取
              </p>
            </div>
          )}

          {result && (
            <ResultCard data={result} onReset={reset} />
          )}
        </div>
      </div>
    </div>
  )
}


/* ==================== 部位知识参考卡 ==================== */
function LocationCard({ info }) {
  // 防御：缺失字段不崩（缓存/异常响应可能不完整）
  //   top_types 元素也可能为 null → 过滤，避免 t.dx / t.group 崩溃
  const topTypes = (Array.isArray(info?.top_types) ? info.top_types : [])
    .filter((t) => t && typeof t === 'object')
  const pct = ((info?.malignant_pct || 0) * 100).toFixed(1)
  const high = (info?.malignant_pct || 0) >= 0.30
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <h3 className="font-semibold text-slate-800">📍 部位参考</h3>
        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
          {info.label}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          high ? 'bg-amber-100 text-amber-700' : 'bg-medical-50 text-medical-700'
        }`}>
          该部位恶性占比约 {pct}%
        </span>
      </div>

      <p className="text-xs text-slate-500 mb-3">
        以下为该部位最常见的病变类型（来自公开数据集的群体统计，n={info.n}）
      </p>

      <ul className="space-y-2">
        {topTypes.map((t) => (
          <li key={t.dx} className="flex items-center gap-3 text-sm">
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
              t.group === 'malignant' ? 'bg-danger-500' : 'bg-medical-400'
            }`} />
            <span className="text-slate-700 w-28 shrink-0">{t.name}</span>
            <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  t.group === 'malignant' ? 'bg-danger-400' : 'bg-medical-400'
                }`}
                style={{ width: `${Math.min(100, t.pct * 100)}%` }}
              />
            </div>
            <span className="text-xs text-slate-400 w-10 text-right shrink-0">
              {(t.pct * 100).toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>

      {info.top_malignant && (
        <p className="mt-3 text-xs text-slate-500 leading-relaxed">
          该部位最高发的恶性类型为「{info.top_malignant.name}」。
        </p>
      )}
      <p className="mt-2 text-xs text-slate-400 leading-relaxed">
        ⓘ {info.disclaimer}
      </p>
    </div>
  )
}

/* ==================== 结果卡片 ==================== */
function ResultCard({ data, onReset }) {
  const { result, advice, image_url, record_id, saved, type_reference, location_reference,
          gradcam, explanation } = data
  const isMalignant = result.label === 'malignant'
  const pct = (result.probability * 100).toFixed(2)
  // 防御：后端应保证这些字段存在，但缓存/异常响应可能缺失 → 给安全默认值，避免整页白屏
  const actList = Array.isArray(advice?.actions) ? advice.actions : []
  const advText = advice?.text || ''
  const ta = advice?.type_advice
  const taActions = Array.isArray(ta?.actions) ? ta.actions : []

  const theme = isMalignant
    ? {
        bg: 'bg-danger-50',
        border: 'border-danger-200',
        text: 'text-danger-600',
        badge: 'bg-danger-500',
        bar: 'bg-danger-500',
      }
    : {
        bg: 'bg-safe-50',
        border: 'border-safe-200',
        text: 'text-safe-600',
        badge: 'bg-safe-500',
        bar: 'bg-safe-500',
      }

  return (
    <div className="space-y-4 fade-in-up">
      {/* 结论 */}
      <div className={`rounded-xl border ${theme.border} ${theme.bg} p-6 shadow-sm`}>
        <div className="flex items-start gap-4">
          <div
            className={`w-14 h-14 rounded-full ${theme.badge} text-white flex items-center justify-center text-2xl shrink-0 shadow`}
          >
            {isMalignant ? '⚠' : '✓'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-slate-500 mb-1">检测结果</div>
            <div className={`text-2xl font-bold ${theme.text}`}>
              {result.label_cn}
              <span className="text-sm font-normal text-slate-500 ml-2">
                ({isMalignant ? 'malignant' : 'benign'})
              </span>
            </div>
            <div className="mt-3">
              <div className="flex justify-between text-xs text-slate-600 mb-1">
                <span>置信度</span>
                <span className="font-mono font-semibold">{pct}%</span>
              </div>
              <div className="h-2 rounded-full bg-white/70 overflow-hidden">
                <div
                  className={`h-full ${theme.bar} transition-all duration-700`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
            <div className="flex gap-4 mt-3 text-xs text-slate-500">
              <span>恶性概率 <b className="font-mono">{(result.malignant_prob * 100).toFixed(1)}%</b></span>
              <span>良性概率 <b className="font-mono">{(result.benign_prob * 100).toFixed(1)}%</b></span>
              <span>耗时 <b className="font-mono">{result.infer_ms.toFixed(0)}ms</b></span>
            </div>
          </div>
        </div>
      </div>

      {/* 病变类型参考（7 类细分，辅助信息） */}
      {type_reference?.top1 && <TypeReferenceCard ref_data={type_reference} />}

      {/* 部位知识参考（科普，不参与判定） */}
      {location_reference && <LocationCard info={location_reference} />}

      {/* 建议 */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <h3 className="font-semibold text-slate-800 mb-2">💡 健康建议</h3>
        <p className="text-sm text-slate-600 leading-relaxed">{advText}</p>
        <ul className="mt-3 space-y-2">
          {actList.map((a, i) => (
            <li key={i} className="flex gap-2 text-sm text-slate-600">
              <span className={`${theme.text} shrink-0`}>•</span>
              <span>{a}</span>
            </li>
          ))}
        </ul>

        {/* 按病变类型的细分建议（类型模型就绪时才有） */}
        {ta && (
          <div className="mt-4 pt-4 border-t border-slate-100">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="text-sm font-semibold text-slate-800">
                🩺 针对「{ta.name || '该类型'}」的补充建议
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                ta.urgency === '高度关注'
                  ? 'bg-danger-100 text-danger-700'
                  : ta.urgency === '需要就诊'
                    ? 'bg-amber-100 text-amber-700'
                    : 'bg-medical-50 text-medical-700'
              }`}>
                {ta.urgency}
              </span>
              <span className="text-xs text-slate-400">
                类型置信度 {((ta.prob || 0) * 100).toFixed(1)}%
              </span>
            </div>
            <p className="text-sm text-slate-600 leading-relaxed mb-3">
              {ta.focus}
            </p>
            <ul className="space-y-2">
              {taActions.map((a, i) => (
                <li key={i} className="flex gap-2 text-sm text-slate-600">
                  <span className="text-slate-400 shrink-0">·</span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
            {ta.disclaimer && (
              <p className="mt-3 text-xs text-slate-400 leading-relaxed">
                ⓘ {ta.disclaimer}
              </p>
            )}
          </div>
        )}
      </div>

      {/* 操作 */}
      <div className="flex gap-3">
        <button
          onClick={onReset}
          className="flex-1 py-2.5 rounded-lg bg-medical-600 text-white font-medium hover:bg-medical-700 transition shadow-sm"
        >
          再检测一张
        </button>
        {saved && record_id && (
          <Link
            to="/history"
            className="flex-1 py-2.5 rounded-lg border border-medical-600 text-medical-600 font-medium hover:bg-medical-50 transition text-center"
          >
            查看历史记录
          </Link>
        )}
      </div>

      {/* ============ 模型可解释性分析（结论之后，供深入了解模型行为）============ */}
      {(gradcam?.images?.length > 0 || explanation) && (
        <>
          <div className="flex items-center gap-3 pt-2">
            <div className="h-px flex-1 bg-slate-200" />
            <span className="text-xs font-medium text-slate-400 whitespace-nowrap">
              🔬 模型解释（进阶）
            </span>
            <div className="h-px flex-1 bg-slate-200" />
          </div>
          <ExplainPanel gradcam={gradcam} explanation={explanation} />
        </>
      )}

      <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
        {data.disclaimer}
      </div>
    </div>
  )
}

/* ==================== 病变类型参考卡片（7 类细分） ==================== */function TypeReferenceCard({ ref_data }) {
  const [expanded, setExpanded] = useState(false)
  const { top1, topk = [], all_probs = {}, model_acc, disclaimer } = ref_data
  // 防御：top1 / topk 元素可能为 null（异常响应或旧缓存）→ 全部过滤，避免渲染期崩溃
  const safeTop1 = top1 && typeof top1 === 'object' ? top1 : null
  const safeTopk = (Array.isArray(topk) ? topk : []).filter((t) => t && typeof t === 'object')
  if (!safeTop1) return null
  const accPct = model_acc ? (model_acc * 100).toFixed(0) : '74'
  const isMalignantType = safeTop1.group === 'malignant'

  // 7 类按概率降序（用于展开视图）
  const allSorted = Object.entries(all_probs)
    .map(([code, prob]) => {
      const hit = safeTopk.find((t) => t.code === code)
      return { code, prob, name: hit?.name || code, group: hit?.group, desc: hit?.desc }
    })
    .sort((a, b) => b.prob - a.prob)

  const barColor = (group) => (group === 'malignant' ? 'bg-danger-500' : 'bg-medical-500')

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="flex items-start justify-between gap-2 mb-3">
        <h3 className="font-semibold text-slate-800 flex items-center gap-2">
          🔍 病变类型参考
        </h3>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200 shrink-0">
          参考信息 · 准确性约 {accPct}%
        </span>
      </div>

      {/* Top-1 */}
      <div
        className={`rounded-lg border p-3 mb-3 ${
          isMalignantType
            ? 'bg-danger-50 border-danger-200'
            : 'bg-medical-50 border-medical-100'
        }`}
      >
        <div className="flex items-baseline justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs text-slate-500 mb-0.5">模型最倾向的类型</div>
            <div
              className={`text-lg font-bold truncate ${
                isMalignantType ? 'text-danger-600' : 'text-medical-700'
              }`}
            >
              {safeTop1.name}
              <span className="text-xs font-normal text-slate-400 ml-2 font-mono">
                {safeTop1.code}
              </span>
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-[10px] text-slate-500">概率</div>
            <div className="font-mono font-bold text-slate-700">
              {((safeTop1.prob || 0) * 100).toFixed(1)}%
            </div>
          </div>
        </div>
        {safeTop1.desc && (
          <p className="text-xs text-slate-600 mt-2 leading-relaxed">{safeTop1.desc}</p>
        )}
        <div className="mt-2">
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full ${
              isMalignantType
                ? 'bg-danger-500 text-white'
                : 'bg-medical-600 text-white'
            }`}
          >
            归属：{isMalignantType ? '恶性' : '良性'}
          </span>
        </div>
      </div>

      {/* Top-3 概率条 */}
      <div className="space-y-2">
        {safeTopk.slice(0, 3).map((t, i) => (
          <div key={t.code}>
            <div className="flex justify-between text-xs text-slate-600 mb-1">
              <span className="truncate">
                <span className="text-slate-400 font-mono mr-1">#{i + 1}</span>
                {t.name}
              </span>
              <span className="font-mono shrink-0 ml-2">{(t.prob * 100).toFixed(1)}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <div
                className={`h-full ${barColor(t.group)} transition-all duration-700`}
                style={{ width: `${Math.max(t.prob * 100, 1)}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* 展开：7 类完整分布 */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="mt-3 text-xs text-medical-600 hover:text-medical-700 hover:underline"
      >
        {expanded ? '▲ 收起 7 类完整分布' : '▼ 查看全部 7 类概率分布'}
      </button>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-slate-100 space-y-1.5">
          {allSorted.map((t) => (
            <div key={t.code} className="flex items-center gap-2 text-xs">
              <span className="w-24 shrink-0 text-slate-600 truncate">{t.name}</span>
              <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={`h-full ${barColor(t.group)}`}
                  style={{ width: `${Math.max(t.prob * 100, 1)}%` }}
                />
              </div>
              <span className="w-12 text-right font-mono text-slate-500 shrink-0">
                {(t.prob * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      )}

      {/* 免责说明（后端返回） */}
      {disclaimer && (
        <p className="mt-3 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 leading-relaxed">
          ⚠️ {disclaimer}
        </p>
      )}
    </div>
  )
}

