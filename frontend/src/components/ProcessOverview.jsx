/**
 * 全景闭环图（SVG）
 *
 * 仿 trajectory.ai「The Vision」的全景示意：
 *   左侧线框立方体（输入/核心） → 上方发光球体（数据层）
 *   → 右侧递增面板组（输出/界面） → 曲线回流回立方体（闭环）
 * 曲线是实线弧 + 小圆点节点 + 箭头，明确"顺时针闭路"。
 *
 * 只在「未选择步骤」时展示，选中后镜头放大推进到对应场景。
 */
export default function ProcessOverview({ onPick, labels = [] }) {
  return (
    <svg className="overview" viewBox="0 0 100 62" aria-hidden="true">
      <defs>
        <linearGradient id="ov-line" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#d8f0ff" stopOpacity=".7" />
          <stop offset=".5" stopColor="#ffffff" stopOpacity="1" />
          <stop offset="1" stopColor="#bfe6ff" stopOpacity=".8" />
        </linearGradient>
        <radialGradient id="ov-globe">
          <stop offset="0" stopColor="#ffffff" stopOpacity=".95" />
          <stop offset=".55" stopColor="#8fd4ff" stopOpacity=".45" />
          <stop offset="1" stopColor="#4aa8e0" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ov-core">
          <stop offset="0" stopColor="#ffffff" stopOpacity=".9" />
          <stop offset="1" stopColor="#5ec8ff" stopOpacity="0" />
        </radialGradient>
        <marker id="ov-arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="3.6" markerHeight="3.6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#dff1ff" />
        </marker>
      </defs>

      {/* 十字网格分割线 */}
      <g className="ov-grid-lines">
        <line x1="34" y1="0" x2="34" y2="62" />
        <line x1="0" y1="26" x2="100" y2="26" />
      </g>

      {/* 闭环主曲线：立方体 → 球体 → 面板组 → 回流立方体 */}
      <path
        className="ov-loop"
        d="M 22 44 C 22 26, 34 18, 47 17
           C 58 16, 62 24, 70 30
           C 78 36, 84 42, 84 48
           C 84 56, 60 58, 40 57
           C 28 56.5, 22 52, 22 44"
        fill="none" stroke="url(#ov-line)" strokeWidth="0.6"
        strokeDasharray="1.4 1"
      />

      {/* 流向箭头：沿曲线切线摆放，标出顺时针流转方向 */}
      {[
        { x: 36, y: 18.6, r: 32 },     // 立方体 → 球体
        { x: 66, y: 26.4, r: 52 },     // 球体 → 面板组
        { x: 84.4, y: 52, r: 92 },     // 面板组 → 回流
        { x: 34, y: 57.6, r: 180 },    // 回流 → 立方体
      ].map((a, i) => (
        <path
          key={i}
          d="M -1.5 -1.1 L 1.6 0 L -1.5 1.1 Z"
          fill="#eaf7ff"
          className="ov-arrow"
          transform={`translate(${a.x} ${a.y}) rotate(${a.r})`}
          style={{ animationDelay: `${i * 0.5}s` }}
        />
      ))}

      {/* 曲线上的节点小圆点 */}
      {[[48, 17], [62, 25], [76, 33], [84, 46], [62, 57], [36, 57], [23, 50]].map(([x, y], i) => (
        <circle key={i} className="ov-node" cx={x} cy={y} r="0.85"
          style={{ animationDelay: `${i * 0.28}s` }} />
      ))}

      {/* 立方体（左中下）：线框 + 内部节点辐射 */}
      <g className="ov-cube ov-glow">
        <path d="M 12 44 L 12 32 L 22 27 L 32 32 L 32 44 L 22 49 Z"
          fill="rgba(120,205,255,.14)" stroke="#cfeeff" strokeWidth="0.5" strokeDasharray="1.2 0.9" />
        <path d="M 12 32 L 22 37 L 32 32 M 22 37 L 22 49"
          fill="none" stroke="#cfeeff" strokeWidth="0.4" strokeDasharray="1.2 0.9" opacity=".85" />
        <circle cx="22" cy="38.5" r="4.2" fill="url(#ov-core)" />
        <circle cx="22" cy="38.5" r="1.1" fill="#ffffff" />
        {[[12, 32], [32, 32], [12, 44], [32, 44], [22, 27], [22, 49]].map(([x, y], i) => (
          <line key={i} x1="22" y1="38.5" x2={x} y2={y} className="ov-spoke"
            style={{ animationDelay: `${i * 0.2}s` }} />
        ))}
      </g>

      {/* 球体（中上）：发光 + 内部星点 */}
      <g className="ov-globe-g ov-glow">
        <circle cx="50" cy="18" r="10" fill="url(#ov-globe)" />
        <circle cx="50" cy="18" r="6.6" fill="rgba(140,215,255,.16)" stroke="#cfeeff" strokeWidth="0.45" />
        <circle cx="50" cy="18" r="9" className="ov-globe-ring" />
        {[[46, 15], [52, 14], [55, 19], [48, 21], [45, 19], [51, 22], [53, 17], [47, 17]].map(([x, y], i) => (
          <circle key={i} className="ov-star" cx={x} cy={y} r="0.4"
            style={{ animationDelay: `${i * 0.35}s` }} />
        ))}
      </g>

      {/* 面板组（右中下）：3 个递增的半透明面板 */}
      <g className="ov-panels ov-glow">
        {[[74, 46, 7, 5], [78, 42, 9, 6.4], [82, 37, 11.5, 8]].map(([x, y, w, h], i) => (
          <rect key={i} x={x} y={y} width={w} height={h} rx="0.9"
            fill="rgba(140,215,255,.15)" stroke="#cfeeff" strokeWidth="0.45"
            className="ov-panel" style={{ animationDelay: `${0.35 + i * 0.25}s` }} />
        ))}
      </g>

      {/* 起点光点（淡紫，标记流程起始） */}
      <circle className="ov-flare" cx="30" cy="30" r="1.3" fill="#d9a8ff" />

      {/* 节点标签：让全景图有信息量（对应四个步骤） */}
      <g className="ov-labels">
        <text x="22" y="53.5" textAnchor="middle">图像输入</text>
        <text x="50" y="30.5" textAnchor="middle">模型推理</text>
        <text x="95" y="34" textAnchor="end">结果输出</text>
        <text x="52" y="61" textAnchor="middle">数据回流 · 闭环迭代</text>
      </g>

      {/* 可点击的步骤热区（透明填充，仅作点击命中，视觉上不可见） */}
      <g className="ov-hits">
        <circle cx="22" cy="38" r="9" />
        <circle cx="50" cy="18" r="9" />
        <rect x="72" y="36" width="24" height="18" rx="1" />
        <rect x="44" y="52" width="30" height="9" rx="1" />
      </g>
    </svg>
  )
}
