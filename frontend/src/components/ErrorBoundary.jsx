import { Component } from 'react'

/**
 * 错误边界：捕获子树渲染异常，避免整个页面白屏。
 *
 * 背景：检测结果卡片依赖后端返回的嵌套结构（advice / type_reference /
 * location_reference），任一字段缺失都会在渲染期抛错。React 的错误会
 * 一路冒泡到根节点，导致【整页空白，连导航都没有】—— 用户体验极差。
 *
 * 用法：
 *   <ErrorBoundary fallback={<提示 />}>  <ResultCard ... />  </ErrorBoundary>
 *
 * @param {ReactNode} children  受保护的子树
 * @param {ReactNode|Function} fallback  出错时的替代内容（可传函数接收 error）
 * @param {string} label  出错时打印的标识，便于定位
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // 打印出来便于排查（生产环境可换成上报）
    //   info.componentStack 会指出是哪个组件抛的错 —— 排查白屏的关键线索
    console.error(`[ErrorBoundary${this.props.label ? ':' + this.props.label : ''}]`, error)
    console.error('[ErrorBoundary] 组件栈:', info?.componentStack)
    this.setState({ componentStack: info?.componentStack || '' })
  }

  render() {
    const { error, componentStack } = this.state
    if (!error) return this.props.children

    const { fallback } = this.props
    if (typeof fallback === 'function') return fallback(error)

    return (
      fallback || (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-sm text-amber-700">
          <div className="font-semibold mb-1">⚠️ 这部分内容加载失败</div>
          <p className="text-xs leading-relaxed">
            页面其它功能仍可正常使用。可尝试刷新页面；若持续出现，请把下方信息反馈给开发者。
          </p>
          <code className="block mt-2 text-[11px] text-amber-600 break-all">
            {String(error && error.message ? error.message : error)}
          </code>
          {componentStack && (
            <details className="mt-2">
              <summary className="text-[11px] cursor-pointer text-amber-700">组件栈（排查用）</summary>
              <pre className="mt-1 text-[10px] text-amber-600 whitespace-pre-wrap break-all">
                {componentStack.split('\n').slice(0, 12).join('\n')}
              </pre>
            </details>
          )}
        </div>
      )
    )
  }
}
