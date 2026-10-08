import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { chatApi } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

/* 快捷问题：覆盖最常见的自检疑问 */
const QUICK_QUESTIONS = [
  '痣和黑色素瘤怎么区分？',
  '皮肤上的痣什么情况需要看医生？',
  '基底细胞癌有哪些早期表现？',
  '日常怎么预防皮肤癌？',
  'ABCDE 法则具体怎么看？',
  '发现痣变大变黑了怎么办？',
]

const DISCLAIMER = 'AI 回答仅供健康科普参考，不构成医疗诊断，不能替代医生面诊。如有疑虑或症状加重，请及时就医。'

/* 极简 Markdown 渲染：加粗 / 有序无序列表 / 段落 / 标题 */
function renderMarkdown(text) {
  if (!text) return null
  const lines = String(text).split('\n')
  const out = []
  let listBuf = []

  const flushList = () => {
    if (!listBuf.length) return
    out.push(
      <ul key={`ul-${out.length}`} className="my-2 space-y-1 pl-1">
        {listBuf.map((li, i) => (
          <li key={i} className="flex gap-2 text-sm leading-relaxed">
            <span className="text-medical-500 shrink-0 mt-0.5">•</span>
            <span dangerouslySetInnerHTML={{ __html: inline(li) }} />
          </li>
        ))}
      </ul>
    )
    listBuf = []
  }

  const inline = (s) =>
    String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-slate-800">$1</strong>')
      .replace(/`(.+?)`/g, '<code class="px-1 py-0.5 rounded bg-slate-100 text-[12px] font-mono">$1</code>')

  lines.forEach((raw, idx) => {
    const line = raw.trim()
    const li = line.match(/^(?:[-*•]|\d+[.、)])\s*(.+)$/)
    if (li) {
      listBuf.push(li[1])
      return
    }
    flushList()
    if (!line) return
    const h = line.match(/^(#{1,4})\s*(.+)$/)
    if (h) {
      out.push(
        <p key={idx} className="mt-3 mb-1 font-semibold text-slate-800 text-sm"
           dangerouslySetInnerHTML={{ __html: inline(h[2]) }} />
      )
      return
    }
    out.push(
      <p key={idx} className="my-1.5 text-sm leading-relaxed text-slate-700"
         dangerouslySetInnerHTML={{ __html: inline(line) }} />
    )
  })
  flushList()
  return out
}

/* 头像 */
function Avatar({ role }) {
  return role === 'user' ? (
    <div className="w-8 h-8 rounded-full bg-medical-100 text-medical-700 flex items-center justify-center text-xs font-semibold shrink-0">
      我
    </div>
  ) : (
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-medical-500 to-medical-600 text-white flex items-center justify-center text-sm shrink-0">
      ⚕
    </div>
  )
}

export default function ChatPage() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [image, setImage] = useState(null)         // { file, url }
  const [sending, setSending] = useState(false)
  const [loadingMsgs, setLoadingMsgs] = useState(false)
  const [error, setError] = useState('')
  const [modelStatus, setModelStatus] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)   // 桌面端可折叠；移动端默认收起

  const listRef = useRef(null)
  const fileRef = useRef(null)

  /* ---------- 模型状态（Ollama 是否就绪） ---------- */
  useEffect(() => {
    chatApi.status()
      .then((d) => setModelStatus(d))
      .catch(() => setModelStatus({ ok: false, error: '无法获取模型状态' }))
  }, [])

  /* ---------- 会话列表 ---------- */
  const loadSessions = useCallback(async () => {
    try {
      const d = await chatApi.sessions({ limit: 50 })
      setSessions(d.items || [])
    } catch (e) {
      /* 列表失败不阻塞对话 */
    }
  }, [])

  useEffect(() => {
    if (authLoading) return
    if (!user) {
      navigate('/login', { state: { from: '/chat' } })
      return
    }
    loadSessions()
  }, [user, authLoading, loadSessions, navigate])

  /* 移动端默认收起侧栏 */
  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 768) setSidebarOpen(false)
  }, [])

  /* ---------- 打开会话 ---------- */
  const openSession = async (sid) => {
    setSessionId(sid)
    setLoadingMsgs(true)
    setError('')
    try {
      const d = await chatApi.session(sid)
      setMessages(d.messages || [])
    } catch (e) {
      setError('加载会话失败')
      setMessages([])
    } finally {
      setLoadingMsgs(false)
    }
  }

  /* ---------- 自动滚到底 ---------- */
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, sending])

  /* ---------- 新对话 ---------- */
  const newChat = () => {
    setSessionId(null)
    setMessages([])
    setInput('')
    setError('')
    clearImage()
    if (typeof window !== 'undefined' && window.innerWidth < 768) setSidebarOpen(false)
  }

  /* ---------- 图片 ---------- */
  const pickImage = (f) => {
    if (!f) return
    if (!/^image\/(jpeg|png|bmp|webp)$/.test(f.type)) {
      setError('图片格式不支持（JPG / PNG / BMP / WEBP）')
      return
    }
    if (f.size > 10 * 1024 * 1024) {
      setError('图片过大（上限 10MB）')
      return
    }
    setError('')
    setImage({ file: f, url: URL.createObjectURL(f) })
  }

  const clearImage = () => {
    if (image?.url) URL.revokeObjectURL(image.url)
    setImage(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  /* ---------- 发送 ---------- */
  const send = async (text) => {
    const q = (text !== undefined ? text : input).trim()
    if ((!q && !image) || sending) return

    setError('')
    setInput('')
    setSending(true)

    // 乐观渲染用户消息
    const optimistic = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      content: q,
      has_image: !!image,
      image_url: image?.url || null,
      created_at: new Date().toISOString(),
    }
    setMessages((m) => [...m, optimistic])

    const imgFile = image?.file || null
    clearImage()

    try {
      // 模型首次加载可能较久，chatApi.send 内部已把超时放宽到 5 分钟
      const d = (await chatApi.send({ question: q, sessionId, image: imgFile })) || {}
      if (d.session_id) setSessionId(d.session_id)
      // 用服务端返回的真实消息替换乐观条目
      setMessages((m) => {
        const base = m.filter((x) => x.id !== optimistic.id)
        const next = [...base]
        if (d.user) next.push(d.user)
        else next.push(optimistic)
        if (d.assistant) next.push(d.assistant)
        return next
      })
      if (d.session_id) loadSessions()
      if (!d.ok) setError(d.error || '模型暂时不可用，请稍后重试')
    } catch (e) {
      setError(e?.message || '发送失败，请稍后重试')
      setMessages((m) => m.filter((x) => x.id !== optimistic.id))
    } finally {
      setSending(false)
    }
  }

  /* ---------- 删除会话 ---------- */
  const delSession = async (sid, e) => {
    e?.stopPropagation()
    if (!window.confirm('删除这个会话？该会话的聊天记录与上传图片会一并删除。')) return
    try {
      await chatApi.removeSession(sid)
      if (sid === sessionId) newChat()
      loadSessions()
    } catch (err) {
      setError('删除失败')
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  if (authLoading) {
    return <div className="flex items-center justify-center h-64 text-slate-400">加载中...</div>
  }
  if (!user) return null

  const offline = modelStatus && modelStatus.ok === false

  return (
    <div className="bg-white min-h-[calc(100vh-4rem)]">
      <div className="flex h-[calc(100vh-4rem)]">

        {/* ============ 左：会话列表（可折叠） ============ */}
        <aside
          className={`${sidebarOpen ? 'w-64' : 'w-0'} transition-all duration-200 overflow-hidden
                      border-r border-slate-200 bg-slate-50/60 shrink-0 hidden md:block`}
        >
          <div className="w-64 h-full flex flex-col">
            <div className="p-3 border-b border-slate-200">
              <button
                onClick={newChat}
                className="w-full py-2 rounded-lg bg-medical-600 text-white text-sm font-medium
                           hover:bg-medical-700 transition flex items-center justify-center gap-1.5"
              >
                <span className="text-base leading-none">＋</span> 新对话
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {sessions.length === 0 && (
                <p className="text-xs text-slate-400 text-center py-6">还没有对话记录</p>
              )}
              {sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => openSession(s.id)}
                  className={`group px-2.5 py-2 rounded-lg cursor-pointer flex items-start gap-2 transition ${
                    s.id === sessionId
                      ? 'bg-medical-50 border border-medical-200'
                      : 'hover:bg-white border border-transparent'
                  }`}
                >
                  <span className="text-slate-400 mt-0.5 text-xs">💬</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] text-slate-700 truncate">{s.title}</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      {(s.updated_at || '').slice(5, 16)} · {s.msg_count ?? 0} 条
                    </div>
                  </div>
                  <button
                    onClick={(e) => delSession(s.id, e)}
                    title="删除会话"
                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-danger-500
                               text-xs px-1 transition"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* ============ 右：对话区 ============ */}
        <section className="flex-1 flex flex-col min-w-0">

          {/* 顶部工具条 */}
          <div className="px-4 py-2.5 border-b border-slate-200 flex items-center gap-3 shrink-0">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              title="折叠/展开会话列表"
              className="hidden md:inline-flex w-8 h-8 items-center justify-center rounded-lg
                         text-slate-500 hover:bg-slate-100 transition"
            >
              ☰
            </button>
            <div className="flex items-center gap-2 min-w-0">
              <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-medical-500 to-medical-600
                               text-white flex items-center justify-center text-sm shrink-0">⚕</span>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-slate-800 truncate">医疗问答</div>
                <div className="text-[11px] text-slate-400 truncate">
                  {offline ? '模型服务未就绪' : '皮肤健康科普 · 就医指引'}
                </div>
              </div>
            </div>
            <div className="ml-auto flex items-center gap-2">
              {modelStatus && modelStatus.ok && (
                <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-safe-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-safe-500" />
                  {modelStatus.text_model_ready ? '模型就绪' : '模型缺失'}
                </span>
              )}
              <button
                onClick={newChat}
                className="md:hidden px-2.5 py-1.5 rounded-lg text-xs border border-slate-200 text-slate-600"
              >
                新对话
              </button>
            </div>
          </div>

          {/* 模型未就绪提示 */}
          {offline && (
            <div className="mx-4 mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
              ⚠️ 问答模型服务未启动（Ollama）。请在服务器执行 <code className="font-mono">ollama serve</code>
              并确认已安装模型后重试。
            </div>
          )}

          {/* 消息列表 */}
          <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-4">
            <div className="max-w-3xl mx-auto">

              {/* 欢迎态 */}
              {messages.length === 0 && !loadingMsgs && (
                <div className="py-6">
                  <div className="flex gap-3">
                    <Avatar role="assistant" />
                    <div className="flex-1 min-w-0">
                      <div className="rounded-2xl rounded-tl-sm bg-slate-50 border border-slate-200 px-4 py-3">
                        <p className="text-sm text-slate-700 leading-relaxed">
                          你好，我是<strong className="text-medical-700">医疗问答助手</strong>。
                          可以问我皮肤健康相关的问题，也可以上传皮肤照片让我一起看看。
                          回答基于医疗微调模型，仅供科普参考，<strong>不能替代医生面诊</strong>。
                        </p>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {QUICK_QUESTIONS.map((q) => (
                          <button
                            key={q}
                            onClick={() => send(q)}
                            disabled={sending || offline}
                            className="px-3 py-1.5 rounded-full text-xs border border-medical-200
                                       text-medical-700 bg-white hover:bg-medical-50 transition
                                       disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {loadingMsgs && (
                <p className="text-center text-sm text-slate-400 py-8">加载会话...</p>
              )}

              {/* 消息 */}
              {messages.map((m) => (
                <div key={m.id} className={`flex gap-3 mb-4 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                  <Avatar role={m.role} />
                  <div className={`min-w-0 max-w-[85%] ${m.role === 'user' ? 'text-right' : ''}`}>
                    {/* 用户上传的图片 */}
                    {m.image_url && (
                      <img
                        src={m.image_url}
                        alt="上传的图片"
                        className="rounded-xl border border-slate-200 mb-2 max-h-56 object-contain ml-auto"
                      />
                    )}
                    {m.content && (
                      m.role === 'user' ? (
                        <div className="inline-block text-left rounded-2xl rounded-tr-sm bg-medical-600
                                        text-white px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words">
                          {m.content}
                        </div>
                      ) : (
                        <div className="text-left rounded-2xl rounded-tl-sm bg-slate-50 border border-slate-200
                                        px-4 py-3">
                          {renderMarkdown(m.content)}
                          {m.model && (
                            <p className="mt-2 pt-2 border-t border-slate-200 text-[10px] text-slate-400">
                              由 {m.model} 生成{m.elapsed_ms ? ` · ${(m.elapsed_ms / 1000).toFixed(1)}s` : ''}
                            </p>
                          )}
                        </div>
                      )
                    )}
                  </div>
                </div>
              ))}

              {/* 思考中 */}
              {sending && (
                <div className="flex gap-3 mb-4">
                  <Avatar role="assistant" />
                  <div className="rounded-2xl rounded-tl-sm bg-slate-50 border border-slate-200 px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          className="w-1.5 h-1.5 rounded-full bg-medical-400 animate-bounce"
                          style={{ animationDelay: `${i * 0.15}s` }}
                        />
                      ))}
                      <span className="text-xs text-slate-400 ml-1">正在思考（首次可能较慢）...</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 错误 */}
          {error && (
            <div className="mx-4 mb-2 rounded-lg border border-danger-200 bg-danger-50 px-3 py-2 text-xs text-danger-700">
              {error}
            </div>
          )}

          {/* 输入区 */}
          <div className="border-t border-slate-200 px-4 py-3 shrink-0">
            <div className="max-w-3xl mx-auto">
              {/* 待发送图片预览 */}
              {image && (
                <div className="mb-2 inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <img src={image.url} alt="待发送" className="w-12 h-12 rounded object-cover" />
                  <div className="text-xs text-slate-600">
                    <div className="max-w-[180px] truncate">{image.file.name}</div>
                    <div className="text-slate-400">{(image.file.size / 1024).toFixed(0)} KB</div>
                  </div>
                  <button onClick={clearImage} className="text-slate-400 hover:text-danger-500 text-sm px-1">✕</button>
                </div>
              )}

              <div className="flex items-end gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/bmp,image/webp"
                  className="hidden"
                  onChange={(e) => pickImage(e.target.files?.[0])}
                />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={sending}
                  title="上传皮肤图片"
                  className="w-10 h-10 rounded-lg border border-slate-200 text-slate-500
                             hover:border-medical-300 hover:text-medical-600 transition
                             disabled:opacity-50 flex items-center justify-center shrink-0"
                >
                  📎
                </button>
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={1}
                  placeholder="输入你的问题…（Enter 发送，Shift+Enter 换行）"
                  className="flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2.5 text-sm
                             focus:outline-none focus:border-medical-400 focus:ring-2 focus:ring-medical-100
                             max-h-32"
                />
                <button
                  onClick={() => send()}
                  disabled={sending || (!input.trim() && !image) || offline}
                  className="px-4 h-10 rounded-lg bg-medical-600 text-white text-sm font-medium
                             hover:bg-medical-700 transition disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                >
                  {sending ? '发送中' : '发送'}
                </button>
              </div>

              <p className="mt-2 text-[11px] text-slate-400 leading-relaxed">
                ⚠️ {DISCLAIMER}
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
