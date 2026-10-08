import { useCallback, useEffect, useState } from 'react'
import { chatApi, recordsApi, tokenStore } from '../api/client'

const FILTERS = [
  { key: '', label: '全部' },
  { key: 'malignant', label: '恶性' },
  { key: 'benign', label: '良性' },
]

/* 主分类：图像检测记录 / 医疗问答记录 */
const TABS = [
  { key: 'detect', label: '图像检测', icon: '🔬' },
  { key: 'chat', label: '医疗问答', icon: '💬' },
]

export default function HistoryPage() {
  const [tab, setTab] = useState('detect')          // 当前分类
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState(null)
  const [page, setPage] = useState(0)
  const LIMIT = 12

  /* 问答分类的独立状态 */
  const [chatItems, setChatItems] = useState([])
  const [chatTotal, setChatTotal] = useState(0)
  const [chatStats, setChatStats] = useState(null)
  const [chatOpen, setChatOpen] = useState(null)     // 打开的会话详情
  const [chatMsgs, setChatMsgs] = useState([])
  const [chatLoadingMsgs, setChatLoadingMsgs] = useState(false)

  /* ---------- 图像检测记录 ---------- */
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, st] = await Promise.all([
        recordsApi.list({ limit: LIMIT, offset: page * LIMIT, label: filter || undefined }),
        recordsApi.stats(),
      ])
      setItems(list.items)
      setTotal(list.total)
      setStats(st)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [page, filter])

  /* ---------- 问答记录 ---------- */
  const loadChat = useCallback(async () => {
    setLoading(true)
    try {
      const d = await chatApi.sessions({ limit: LIMIT, offset: page * LIMIT })
      setChatItems(d.items || [])
      setChatTotal(d.total || 0)
      setChatStats(d.stats || null)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    if (tab === 'detect') load()
    else loadChat()
  }, [tab, load, loadChat])

  /* 首次进入时预取两个分类的统计，让 Tab 上的数字一开始就准确 */
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [st, cs] = await Promise.all([
          recordsApi.stats(),
          chatApi.sessions({ limit: 1 }),
        ])
        if (!alive) return
        setStats((prev) => prev || st)
        setChatStats((prev) => prev || (cs?.stats || { sessions: cs?.total || 0 }))
      } catch (e) {
        /* 预取失败不阻塞页面 */
      }
    })()
    return () => { alive = false }
  }, [])

  /* 切换分类时重置分页/筛选 */
  const switchTab = (k) => {
    if (k === tab) return
    setTab(k)
    setPage(0)
    setFilter('')
    setItems([])
    setChatItems([])
    setDetail(null)
    setChatOpen(null)
  }

  const remove = async (id) => {
    if (!window.confirm('确定要删除这条记录吗？删除后不可恢复。')) return
    try {
      await recordsApi.remove(id)
      setDetail(null)
      load()
    } catch (e) {
      alert('删除失败：' + e.message)
    }
  }

  /* 查看某个问答会话的消息 */
  const openChat = async (s) => {
    setChatOpen(s)
    setChatLoadingMsgs(true)
    setChatMsgs([])
    try {
      const d = await chatApi.session(s.id)
      setChatMsgs(d.messages || [])
    } catch (e) {
      alert('加载对话失败：' + e.message)
      setChatOpen(null)
    } finally {
      setChatLoadingMsgs(false)
    }
  }

  const removeChat = async (sid, e) => {
    e?.stopPropagation()
    if (!window.confirm('删除这个问答会话？聊天记录与上传的图片会一并删除。')) return
    try {
      await chatApi.removeSession(sid)
      if (chatOpen?.id === sid) setChatOpen(null)
      loadChat()
    } catch (err) {
      alert('删除失败：' + err.message)
    }
  }

  const exportCsv = () => {
    const token = tokenStore.get()
    // 用 fetch 带 header 下载（<a> 无法带 Authorization）
    fetch('/api/records/export', { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `检测记录_${new Date().toISOString().slice(0, 10)}.csv`
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch((e) => alert('导出失败：' + e.message))
  }

  const totalPages = Math.ceil((tab === 'detect' ? total : chatTotal) / LIMIT)

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">检测历史</h1>
          <p className="text-sm text-slate-500 mt-1">
            {tab === 'detect'
              ? '查看过往检测记录与结果对比'
              : '查看医疗问答的对话记录'}
          </p>
        </div>
        {tab === 'detect' && (
          <button
            onClick={exportCsv}
            disabled={!total}
            className="px-4 py-2 rounded-lg border border-medical-600 text-medical-600 text-sm font-medium hover:bg-medical-50 disabled:opacity-40 transition"
          >
            ⬇ 导出 CSV
          </button>
        )}
      </div>

      {/* 分类切换：图像检测 / 医疗问答 */}
      <div className="inline-flex p-1 rounded-xl bg-slate-100 mb-6">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => switchTab(t.key)}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition flex items-center gap-1.5 ${
              tab === t.key
                ? 'bg-white text-medical-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <span>{t.icon}</span> {t.label}
            <span className="text-[11px] opacity-60">
              {t.key === 'detect' ? (stats?.total ?? 0) : (chatStats?.sessions ?? 0)}
            </span>
          </button>
        ))}
      </div>

      {/* ==================== 图像检测 ==================== */}
      {tab === 'detect' && (
        <>
          {/* 统计 */}
          {stats && (
            <div className="grid grid-cols-3 gap-4 mb-6">
              <StatBox label="检测总数" value={stats.total} color="text-slate-800" />
              <StatBox
                label="倾向恶性"
                value={stats.malignant}
                color="text-danger-600"
              />
              <StatBox
                label="倾向良性"
                value={stats.benign}
                color="text-safe-600"
              />
            </div>
          )}

          {/* 筛选 */}
          <div className="flex gap-2 mb-5">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => {
                  setFilter(f.key)
                  setPage(0)
                }}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${
                  filter === f.key
                    ? 'bg-medical-600 text-white shadow-sm'
                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* 列表 */}
          {loading ? (
            <div className="text-center py-16 text-slate-400">加载中...</div>
          ) : items.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-xl border border-slate-200">
              <div className="text-5xl mb-3 opacity-30">📭</div>
              <p className="text-slate-500">暂无检测记录</p>
              <a
                href="/detect"
                className="inline-block mt-4 px-5 py-2 rounded-lg bg-medical-600 text-white text-sm hover:bg-medical-700 transition"
              >
                去检测
              </a>
            </div>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {items.map((it) => (
                <RecordCard
                  key={it.id}
                  item={it}
                  onView={() => setDetail(it)}
                  onDelete={() => remove(it.id)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* ==================== 医疗问答 ==================== */}
      {tab === 'chat' && (
        <>
          {chatStats && (
            <div className="grid grid-cols-2 gap-4 mb-6">
              <StatBox label="会话总数" value={chatStats.sessions} color="text-slate-800" />
              <StatBox label="提问条数" value={chatStats.messages} color="text-medical-600" />
            </div>
          )}

          {loading ? (
            <div className="text-center py-16 text-slate-400">加载中...</div>
          ) : chatItems.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-xl border border-slate-200">
              <div className="text-5xl mb-3 opacity-30">💬</div>
              <p className="text-slate-500">暂无问答记录</p>
              <a
                href="/chat"
                className="inline-block mt-4 px-5 py-2 rounded-lg bg-medical-600 text-white text-sm hover:bg-medical-700 transition"
              >
                去提问
              </a>
            </div>
          ) : (
            <div className="space-y-3">
              {chatItems.map((s) => (
                <div
                  key={s.id}
                  onClick={() => openChat(s)}
                  className="bg-white rounded-xl border border-slate-200 p-4 hover:border-medical-300
                             hover:shadow-sm transition cursor-pointer flex items-start gap-3"
                >
                  <span className="w-9 h-9 rounded-lg bg-medical-50 text-medical-600 flex items-center
                                   justify-center text-base shrink-0">💬</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-800 truncate">{s.title}</div>
                    <div className="text-xs text-slate-400 mt-1">
                      {(s.updated_at || '').replace('T', ' ').slice(0, 16)}
                      {' · '}
                      {s.msg_count ?? 0} 条消息
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-medical-600">查看</span>
                    <button
                      onClick={(e) => removeChat(s.id, e)}
                      title="删除会话"
                      className="text-slate-300 hover:text-danger-500 text-sm px-1 transition"
                    >
                      🗑
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 mt-8">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                className="px-4 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 disabled:opacity-40 hover:bg-slate-50 transition"
              >
                上一页
              </button>
              <span className="text-sm text-slate-500">
                {page + 1} / {totalPages} 页（共 {chatTotal} 条）
              </span>
              <button
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
                className="px-4 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 disabled:opacity-40 hover:bg-slate-50 transition"
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}

      {/* 图像检测分页（仅 detect 分类） */}
      {tab === 'detect' && totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-8">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            className="px-4 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 disabled:opacity-40 hover:bg-slate-50 transition"
          >
            上一页
          </button>
          <span className="text-sm text-slate-500">
            {page + 1} / {totalPages} 页（共 {total} 条）
          </span>
          <button
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
            className="px-4 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 disabled:opacity-40 hover:bg-slate-50 transition"
          >
            下一页
          </button>
        </div>
      )}

      {/* 检测详情弹窗 */}
      {detail && (
        <DetailModal
          item={detail}
          onClose={() => setDetail(null)}
          onDelete={() => remove(detail.id)}
        />
      )}

      {/* 问答会话详情弹窗 */}
      {chatOpen && (
        <ChatDetailModal
          session={chatOpen}
          messages={chatMsgs}
          loading={chatLoadingMsgs}
          onClose={() => setChatOpen(null)}
        />
      )}
    </div>
  )
}

function StatBox({ label, value, color }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 text-center shadow-sm">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </div>
  )
}

function RecordCard({ item, onView, onDelete }) {
  const isMal = item.label === 'malignant'
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md transition group">
      <div className="aspect-video bg-slate-900 relative overflow-hidden">
        <img
          src={item.image_url}
          alt={item.filename}
          className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
          loading="lazy"
        />
        <span
          className={`absolute top-2 right-2 px-2.5 py-1 rounded-full text-xs font-semibold text-white shadow ${
            isMal ? 'bg-danger-500' : 'bg-safe-500'
          }`}
        >
          {item.label_cn}
        </span>
      </div>
      <div className="p-4">
        <div className="text-sm text-slate-700 truncate mb-1">
          {item.filename}
        </div>
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>{item.created_at}</span>
          <span className="font-mono">
            {(item.probability * 100).toFixed(1)}%
          </span>
        </div>
        {item.note && (
          <div className="mt-2 text-xs text-slate-500 bg-slate-50 rounded px-2 py-1 truncate">
            备注：{item.note}
          </div>
        )}
        <div className="flex gap-2 mt-3">
          <button
            onClick={onView}
            className="flex-1 py-1.5 rounded-lg bg-medical-50 text-medical-700 text-xs font-medium hover:bg-medical-100 transition"
          >
            查看详情
          </button>
          <button
            onClick={onDelete}
            className="px-3 py-1.5 rounded-lg bg-danger-50 text-danger-600 text-xs font-medium hover:bg-danger-100 transition"
          >
            删除
          </button>
        </div>
      </div>
    </div>
  )
}

function DetailModal({ item, onClose, onDelete }) {
  const isMal = item.label === 'malignant'
  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-slate-100 flex items-center justify-between sticky top-0 bg-white">
          <h3 className="font-semibold text-slate-800">检测记录详情</h3>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-slate-100 text-slate-400 text-xl leading-none"
          >
            ×
          </button>
        </div>
        <div className="p-5 space-y-4">
          <img
            src={item.image_url}
            alt={item.filename}
            className="w-full max-h-72 object-contain bg-slate-900 rounded-lg"
          />
          <div
            className={`rounded-lg p-4 ${
              isMal
                ? 'bg-danger-50 border border-danger-200'
                : 'bg-safe-50 border border-safe-200'
            }`}
          >
            <div
              className={`text-xl font-bold ${
                isMal ? 'text-danger-600' : 'text-safe-600'
              }`}
            >
              {item.label_cn}
              <span className="text-sm font-normal text-slate-500 ml-2">
                置信度 {(item.probability * 100).toFixed(2)}%
              </span>
            </div>
            <div className="flex gap-4 mt-2 text-xs text-slate-600">
              <span>恶性 {(item.malignant_prob * 100).toFixed(1)}%</span>
              <span>良性 {(item.benign_prob * 100).toFixed(1)}%</span>
              <span>阈值 {item.threshold}</span>
              <span>耗时 {item.infer_ms.toFixed(0)}ms</span>
            </div>
          </div>
          <dl className="text-sm space-y-2">
            <Row label="文件名" value={item.filename} />
            <Row label="检测时间" value={item.created_at} />
            <Row label="备注" value={item.note || '（无）'} />
          </dl>
        </div>
        <div className="p-5 border-t border-slate-100 flex gap-3">
          <button
            onClick={onDelete}
            className="px-5 py-2 rounded-lg bg-danger-50 text-danger-600 text-sm font-medium hover:bg-danger-100 transition"
          >
            删除记录
          </button>
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-lg bg-medical-600 text-white text-sm font-medium hover:bg-medical-700 transition"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1 border-b border-slate-50">
      <dt className="text-slate-500 shrink-0">{label}</dt>
      <dd className="text-slate-700 text-right break-all">{value}</dd>
    </div>
  )
}

/* ==================== 问答会话详情弹窗 ==================== */
function ChatDetailModal({ session, messages, loading, onClose }) {
  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl max-w-3xl w-full max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-3 shrink-0">
          <div className="min-w-0">
            <h3 className="font-semibold text-slate-800 truncate">{session.title}</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              医疗问答 · {(session.updated_at || '').replace('T', ' ').slice(0, 16)}
              {' · '}{messages.length || session.msg_count || 0} 条消息
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-slate-100 text-slate-400 text-xl leading-none shrink-0"
          >
            ×
          </button>
        </div>

        {/* 消息流 */}
        <div className="flex-1 overflow-y-auto p-5 bg-slate-50/50">
          {loading ? (
            <p className="text-center text-sm text-slate-400 py-10">加载对话中...</p>
          ) : messages.length === 0 ? (
            <p className="text-center text-sm text-slate-400 py-10">这个会话还没有消息</p>
          ) : (
            <div className="space-y-4">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-xs shrink-0 ${
                      m.role === 'user'
                        ? 'bg-medical-100 text-medical-700 font-semibold'
                        : 'bg-gradient-to-br from-medical-500 to-medical-600 text-white'
                    }`}
                  >
                    {m.role === 'user' ? '我' : '⚕'}
                  </div>
                  <div className={`min-w-0 max-w-[85%] ${m.role === 'user' ? 'text-right' : ''}`}>
                    {m.image_url && (
                      <img
                        src={m.image_url}
                        alt="上传的图片"
                        className="rounded-lg border border-slate-200 mb-2 max-h-48 object-contain ml-auto"
                      />
                    )}
                    {m.content && (
                      <div
                        className={`inline-block text-left rounded-xl px-3.5 py-2.5 text-sm leading-relaxed
                                    whitespace-pre-wrap break-words ${
                          m.role === 'user'
                            ? 'bg-medical-600 text-white rounded-tr-sm'
                            : 'bg-white border border-slate-200 text-slate-700 rounded-tl-sm'
                        }`}
                      >
                        {m.content}
                      </div>
                    )}
                    {m.model && (
                      <p className="text-[10px] text-slate-400 mt-1">
                        {m.model}
                        {m.elapsed_ms ? ` · ${(m.elapsed_ms / 1000).toFixed(1)}s` : ''}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 底部 */}
        <div className="p-4 border-t border-slate-100 shrink-0">
          <p className="text-[11px] text-slate-400 mb-3 text-center">
            AI 回答仅供健康科普参考，不构成医疗诊断
          </p>
          <button
            onClick={onClose}
            className="w-full py-2 rounded-lg bg-medical-600 text-white text-sm font-medium hover:bg-medical-700 transition"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
