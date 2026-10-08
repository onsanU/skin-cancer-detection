import { useState } from 'react'

/**
 * 密码输入框：下划线样式 + 右侧「显示 / 隐藏」切换按钮
 * 与 .auth-input 视觉完全一致，只是外面包一层相对定位容器放按钮。
 *
 * @param {string}   value
 * @param {Function} onChange  (e) => void
 * @param {string}   label     字段标签文案
 * @param {string}   placeholder
 * @param {boolean}  required
 * @param {string}   autoComplete
 * @param {boolean}  showLabel  是否渲染上方标签（注册页并排时用）
 */
export default function PasswordField({
  value,
  onChange,
  label = '密码',
  placeholder = '请输入密码',
  required = false,
  autoComplete = 'current-password',
  showLabel = true,
}) {
  const [visible, setVisible] = useState(false)

  return (
    <div>
      {showLabel && <span className="auth-label mb-3">{label}</span>}
      <div className="relative">
        <input
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          required={required}
          autoComplete={autoComplete}
          className="auth-input pr-10"
          placeholder={placeholder}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? '隐藏密码' : '显示密码'}
          title={visible ? '隐藏密码' : '显示密码'}
          tabIndex={-1}
          className="auth-eye"
        >
          {visible ? <EyeOff /> : <Eye />}
        </button>
      </div>
    </div>
  )
}

/* 内联 SVG 图标（零依赖，不引图标库） */
function Eye() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2.5 12S5.5 5.5 12 5.5 21.5 12 21.5 12 18.5 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3.2" />
    </svg>
  )
}

function EyeOff() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9.9 5.7A9.6 9.6 0 0 1 12 5.5c6.5 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3 4.1" />
      <path d="M6.4 7.4A17 17 0 0 0 2.5 12S5.5 18.5 12 18.5c1.5 0 2.8-.34 4-.9" />
      <path d="M10 10a2.8 2.8 0 0 0 4 4" />
      <path d="M3 3l18 18" />
    </svg>
  )
}
