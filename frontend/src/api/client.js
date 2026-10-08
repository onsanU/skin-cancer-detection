/**
 * API 客户端 —— 统一封装后端接口调用
 */
import axios from 'axios'

const TOKEN_KEY = 'skin_cancer_token'

export const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// 请求拦截：自动带上 JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：统一错误信息
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY)
    }
    return Promise.reject(new Error(detail || err.message || '请求失败'))
  }
)

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

// ---------- 接口 ----------
export const healthApi = {
  check: () => api.get('/health').then((r) => r.data),
  modelInfo: () => api.get('/model/info').then((r) => r.data),
  /**
   * 探测医疗问答服务（Ollama）是否在线
   * 后端 /api/chat/status 无需登录即可探测模型是否就绪，
   * 但走统一 axios 时会带上过期 JWT 反而 401；首页探测用裸 fetch 更稳。
   */
  chatStatus: () =>
    fetch('/api/chat/status')
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null),
}

export const authApi = {
  register: (data) => api.post('/auth/register', data).then((r) => r.data),
  login: (data) => api.post('/auth/login', data).then((r) => r.data),
  me: () => api.get('/auth/me').then((r) => r.data),
}

export const predictApi = {
  /**
   * 上传图像检测
   * @param {File} file 图像文件
   * @param {Object} opts { threshold, note, location, onProgress }
   */
  detect: (file, opts = {}) => {
    const form = new FormData()
    form.append('file', file)
    if (opts.threshold != null) form.append('threshold', String(opts.threshold))
    if (opts.note) form.append('note', opts.note)
    if (opts.location) form.append('location', opts.location)
    return api
      .post('/predict', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: opts.onProgress,
      })
      .then((r) => r.data)
  },
}

export const recordsApi = {
  list: (params) => api.get('/records', { params }).then((r) => r.data),
  stats: () => api.get('/records/stats').then((r) => r.data),
  detail: (id) => api.get(`/records/${id}`).then((r) => r.data),
  remove: (id) => api.delete(`/records/${id}`).then((r) => r.data),
  exportUrl: () => {
    const token = tokenStore.get()
    return { url: '/api/records/export', token }
  },
}

/** 医疗问答（需登录） */
export const chatApi = {
  status: () => api.get('/chat/status').then((r) => r.data),
  sessions: (params) => api.get('/chat/sessions', { params }).then((r) => r.data),
  session: (id) => api.get(`/chat/sessions/${id}`).then((r) => r.data),
  createSession: (title = '新对话') =>
    api.post('/chat/sessions', { title }).then((r) => r.data),
  removeSession: (id) => api.delete(`/chat/sessions/${id}`).then((r) => r.data),
  /**
   * 发送提问（支持图片）
   * @param {Object} p { question, sessionId, image }
   *   model 首次加载可能较慢，超时放宽到 5 分钟
   */
  send: ({ question, sessionId, image }) => {
    const fd = new FormData()
    if (question) fd.append('question', question)
    if (sessionId) fd.append('session_id', String(sessionId))
    if (image) fd.append('image', image)
    return api
      .post('/chat/send', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 300000,
      })
      .then((r) => r.data)
  },
}
