import { Link } from 'react-router-dom'

/**
 * 认证页布局（登录 / 注册共用）
 * 风格参考 conductorai.com：左文案区 + 右表单区，浅底网格纹理，
 * 深海军蓝巨字标题，亮蓝主按钮，对焦框装饰。
 *
 * @param {string} eyebrow   左上角等宽编号/小标题，如 "01 / 账号登录"
 * @param {string} title     巨字主标题（可传 JSX 以支持换行）
 * @param {string} subtitle  副文案
 * @param {Array}  highlights 左侧要点列表 [{icon, text}]
 * @param {ReactNode} children 右侧表单内容
 */
export default function AuthLayout({ eyebrow, title, subtitle, highlights = [], children }) {
  return (
    <div className="auth-page">
      {/* 顶部品牌条 */}
      <header className="max-w-[85rem] mx-auto px-6 md:px-10 pt-8 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 no-underline">
          <span
            className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-bold"
            style={{ background: 'var(--auth-brand)' }}
          >
            ⚕
          </span>
          <span className="text-[0.9375rem] font-semibold" style={{ color: 'var(--auth-dark)' }}>
            皮肤癌图像检测系统
          </span>
        </Link>
        <Link to="/" className="auth-btn-ghost">
          ← 返回首页
        </Link>
      </header>

      {/* 主体：左右分栏。分栏由 main 的 .auth-split 统一负责（45% 文案 / 55% 表单），
          两个 section 是它的直接子元素；内层不再包一层 grid 重复分栏，
          否则外层切出的 576px 会被再切一次，标题被压成窄条、挤成多行。 */}
      <main className="auth-split w-full max-w-[85rem] mx-auto px-6 md:px-10 py-12 md:py-20">
        {/* ---------- 左侧：文案区 ---------- */}
        <section className="auth-in relative lg:sticky lg:top-20">
          {eyebrow && (
            <div className="auth-eyebrow mb-6 flex items-center gap-3">
              <span style={{ width: 28, height: '1.5px', background: 'var(--auth-brand)', display: 'inline-block' }} />
              {eyebrow}
            </div>
          )}

          <h1 className="auth-display mb-6">{title}</h1>

          {subtitle && (
            <p className="text-base md:text-lg leading-relaxed mb-8" style={{ color: 'var(--auth-body)' }}>
              {subtitle}
            </p>
          )}

          {highlights.length > 0 && (
            <ul className="list-none p-0 m-0 mb-8 space-y-3">
              {highlights.map((h, i) => (
                <li key={i} className="flex items-start gap-3 text-sm" style={{ color: 'var(--auth-body)' }}>
                  <span
                    className="shrink-0 mt-0.5 w-5 h-5 rounded-md flex items-center justify-center text-[11px] font-bold"
                    style={{ background: 'var(--auth-bg-soft)', color: 'var(--auth-brand)' }}
                  >
                    {h.icon}
                  </span>
                  <span className="leading-relaxed">{h.text}</span>
                </li>
              ))}
            </ul>
          )}

          {/* 医疗免责声明 */}
          <div
            className="text-xs leading-relaxed rounded-lg px-4 py-3"
            style={{
              border: '1.5px solid var(--auth-error-soft)',
              background: 'rgba(255, 79, 79, 0.04)',
              color: 'var(--auth-body)',
            }}
          >
            <span className="font-semibold" style={{ color: 'var(--auth-error)' }}>⚠ 医疗免责声明　</span>
            本系统仅作为皮肤健康自检的辅助工具，检测结果由 AI 模型生成，仅供参考，
            不构成医疗诊断，不能替代专业医生的诊断与治疗。
          </div>
        </section>

        {/* ---------- 右侧：表单区 ---------- */}
        <section className="auth-in relative">
          {/* 对焦框装饰 */}
          <div className="relative p-6 md:p-10" style={{ background: 'rgba(255,255,255,0.72)', border: '1.5px solid var(--auth-border)', borderRadius: '1rem' }}>
            <span className="auth-corner auth-corner-tl" />
            <span className="auth-corner auth-corner-tr" />
            <span className="auth-corner auth-corner-bl" />
            <span className="auth-corner auth-corner-br" />
            {children}
          </div>
        </section>
      </main>

      {/* 页脚 */}
      <footer className="max-w-[85rem] mx-auto px-6 md:px-10 pb-8">
        <div
          className="pt-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs"
          style={{ borderTop: '1.5px solid var(--auth-border)', color: 'var(--auth-muted)' }}
        >
          <span>© 2026 皮肤癌图像检测系统 · 仅供学习研究使用</span>
          <span className="font-mono">v1.0 · ResNet50 Ensemble</span>
        </div>
      </footer>
    </div>
  )
}
