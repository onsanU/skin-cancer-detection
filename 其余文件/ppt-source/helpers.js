/**
 * 共享布局函数 —— 明亮医疗风
 * 配色：白底 + 医疗蓝 + 清新绿，卡片式布局
 * 所有函数接受 slide 对象（pres.addSlide() 的返回值）
 */

const C = {
  // 背景
  bg: 'F7FAFC',           // 页面浅灰白
  white: 'FFFFFF',        // 卡片白
  // 主色 - 医疗蓝
  blue: '0284C7',
  blueLight: 'E0F2FE',
  blueSoft: 'F0F9FF',
  blueDeep: '075985',
  // 辅色 - 清新绿
  green: '10B981',
  greenLight: 'D1FAE5',
  // 强调 - 橙（用于难点/警示）
  amber: 'F59E0B',
  amberLight: 'FEF3C7',
  // 强调 - 紫（用于优化点）
  purple: '8B5CF6',
  purpleLight: 'EDE9FE',
  // 文字
  text: '1E293B',         // 主文字（深灰蓝）
  textSub: '64748B',      // 次级文字
  textLight: '94A3B8',    // 辅助文字
  // 边框
  border: 'E2E8F0',
  borderBlue: 'BAE6FD',
  // 危险（用于恶性/问题）
  red: 'EF4444',
  redLight: 'FEE2E2',
  // 扩展辅色（问答 / 部署 / 后台）
  teal: '0D9488',
  tealLight: 'CCFBF1',
  magenta: 'DB2777',
  magentaLight: 'FCE7F3',
};

const FONT = '微软雅黑';
const W = 10, H = 5.625;

/* ---------- 基础布局 ---------- */
function blank(pres) {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  return s;
}

/* ---------- 封面 ---------- */
function cover(slide, { title, subtitle, meta = [], accent = C.blue }) {
  // 顶部色带
  slide.addShape('rect', { x: 0, y: 0, w: W, h: 0.12, fill: { color: accent } });
  // 右上装饰圆环
  slide.addShape('ellipse', {
    x: 8.2, y: 0.35, w: 1.5, h: 1.5,
    fill: { color: C.blueLight }, line: { color: C.blueLight },
  });
  slide.addShape('ellipse', {
    x: 9.0, y: 1.1, w: 0.85, h: 0.85,
    fill: { color: C.white }, line: { color: C.borderBlue, width: 1 },
  });
  // 左侧竖条
  slide.addShape('rect', { x: 0.9, y: 1.75, w: 0.09, h: 1.5, fill: { color: accent } });

  slide.addText(title, {
    x: 1.2, y: 1.7, w: 7.2, h: 0.85,
    fontSize: 36, bold: true, color: C.text, fontFace: FONT, valign: 'middle',
  });
  slide.addText(subtitle, {
    x: 1.2, y: 2.6, w: 7.2, h: 0.5,
    fontSize: 16, color: C.textSub, fontFace: FONT,
  });

  // 元信息胶囊
  let mx = 1.2;
  meta.forEach((m) => {
    const w = Math.max(1.15, m.length * 0.135 + 0.42);
    slide.addShape('roundRect', {
      x: mx, y: 3.45, w, h: 0.36, rectRadius: 0.18,
      fill: { color: C.white }, line: { color: C.borderBlue, width: 1 },
    });
    slide.addText(m, {
      x: mx, y: 3.45, w, h: 0.36,
      fontSize: 10.5, color: C.blueDeep, fontFace: FONT,
      align: 'center', valign: 'middle',
    });
    mx += w + 0.16;
  });

  // 底部条
  slide.addShape('rect', { x: 0, y: H - 0.09, w: W, h: 0.09, fill: { color: accent } });
}

/* ---------- 页面标题栏 ---------- */
function titleBar(slide, title, sub, page, accent = C.blue) {
  slide.addShape('rect', { x: 0.55, y: 0.42, w: 0.075, h: 0.32, fill: { color: accent } });
  slide.addText(title, {
    x: 0.78, y: 0.33, w: 7.0, h: 0.5,
    fontSize: 20, bold: true, color: C.text, fontFace: FONT, valign: 'middle',
  });
  if (sub) {
    slide.addText(sub, {
      x: 0.78, y: 0.86, w: 7.6, h: 0.3,
      fontSize: 10.5, color: C.textLight, fontFace: FONT,
    });
  }
  // 右上页码
  if (page != null) {
    slide.addShape('roundRect', {
      x: 9.05, y: 0.42, w: 0.42, h: 0.32, rectRadius: 0.09,
      fill: { color: C.blueSoft }, line: { color: C.borderBlue, width: 0.75 },
    });
    slide.addText(String(page), {
      x: 9.05, y: 0.42, w: 0.42, h: 0.32,
      fontSize: 10.5, bold: true, color: C.blue, fontFace: FONT,
      align: 'center', valign: 'middle',
    });
  }
}

/* ---------- 卡片 ---------- */
function card(slide, { x, y, w, h, fill = C.white, line = C.border, radius = 0.1 }) {
  slide.addShape('roundRect', {
    x, y, w, h, rectRadius: radius,
    fill: { color: fill },
    line: { color: line, width: 1 },
  });
}

/* ---------- 卡片 + 标题 ---------- */
function cardTitle(slide, x, y, w, text, opts = {}) {
  const { size = 12.5, color = C.blueDeep, icon = '' } = opts;
  slide.addText(icon ? `${icon}  ${text}` : text, {
    x, y, w, h: 0.3,
    fontSize: size, bold: true, color, fontFace: FONT, valign: 'middle',
  });
}

/* ---------- 列表（纯文本符号，避免 bullet 渲染坑） ---------- */
function bullets(slide, x, y, w, items, opts = {}) {
  const { size = 11, color = C.text, gap = 0.36, lineColor = C.blue } = opts;
  items.forEach((it, i) => {
    slide.addText('•', {
      x, y: y + i * gap, w: 0.2, h: 0.3,
      fontSize: size, bold: true, color: lineColor, fontFace: FONT, valign: 'middle',
    });
    const isStr = typeof it === 'string';
    slide.addText(isStr ? it : it.text, {
      x: x + 0.22, y: y + i * gap, w: w - 0.22, h: 0.3,
      fontSize: isStr ? size : (it.size || size),
      bold: !isStr && it.bold,
      color: isStr ? color : (it.color || color),
      fontFace: FONT, valign: 'middle',
    });
  });
}

/* ---------- 标签胶囊 ---------- */
function tag(slide, x, y, text, opts = {}) {
  const { fill = C.blueLight, color = C.blueDeep, w = 0.95, h = 0.26, size = 9.5 } = opts;
  slide.addShape('roundRect', {
    x, y, w, h, rectRadius: h / 2,
    fill: { color: fill }, line: { color: fill },
  });
  slide.addText(text, {
    x, y, w, h, fontSize: size, bold: true, color, fontFace: FONT,
    align: 'center', valign: 'middle',
  });
}

/* ---------- 数据卡（大数字 + 说明） ---------- */
function statCard(slide, x, y, w, h, value, label, opts = {}) {
  const { accent = C.blue, fill = C.white, vsize = 22 } = opts;
  card(slide, { x, y, w, h, fill });
  slide.addShape('rect', { x, y, w: 0.06, h, fill: { color: accent } });
  slide.addText(value, {
    x: x + 0.1, y: y + 0.12, w: w - 0.2, h: h * 0.5,
    fontSize: vsize, bold: true, color: accent, fontFace: FONT,
    align: 'center', valign: 'middle',
  });
  slide.addText(label, {
    x: x + 0.1, y: y + h * 0.55, w: w - 0.2, h: h * 0.38,
    fontSize: 10, color: C.textSub, fontFace: FONT,
    align: 'center', valign: 'middle',
  });
}

/* ---------- 简易表格 ---------- */
function table(slide, x, y, w, rows, opts = {}) {
  const { colW, fontSize = 10, headerFill = C.blue, headerColor = C.white,
          headH = 0.34, rowH = 0.32, highlightRow = -1 } = opts;
  const totalW = w;
  const cw = colW || rows[0].map(() => totalW / rows[0].length);

  rows.forEach((row, ri) => {
    const ry = y + (ri === 0 ? 0 : headH + (ri - 1) * rowH);
    const rh = ri === 0 ? headH : rowH;
    const isHead = ri === 0;
    const isHl = ri === highlightRow;
    let cx = x;
    row.forEach((cell, ci) => {
      slide.addShape('rect', {
        x: cx, y: ry, w: cw[ci], h: rh,
        fill: { color: isHead ? headerFill : (isHl ? C.blueSoft : (ri % 2 ? C.white : 'FBFDFE')) },
        line: { color: isHead ? headerFill : C.border, width: 0.75 },
      });
      slide.addText(String(cell), {
        x: cx + 0.06, y: ry, w: cw[ci] - 0.12, h: rh,
        fontSize, bold: isHead || isHl,
        color: isHead ? headerColor : (isHl ? C.blueDeep : C.text),
        fontFace: FONT, align: ci === 0 ? 'left' : 'center', valign: 'middle',
      });
      cx += cw[ci];
    });
  });
}

/* ---------- 底部提示条 ---------- */
function noteBar(slide, text, opts = {}) {
  const { fill = C.blueSoft, color = C.blueDeep, line = C.borderBlue, y = 4.82 } = opts;
  slide.addShape('roundRect', {
    x: 0.55, y, w: 8.9, h: 0.42, rectRadius: 0.08,
    fill: { color: fill }, line: { color: line, width: 1 },
  });
  slide.addText(text, {
    x: 0.72, y, w: 8.6, h: 0.42,
    fontSize: 10, color, fontFace: FONT, valign: 'middle',
  });
}

/* ---------- 页脚 ---------- */
function footer(slide, text = '皮肤癌图像检测系统') {
  slide.addShape('rect', { x: 0, y: H - 0.06, w: W, h: 0.06, fill: { color: C.blueLight } });
  slide.addText(text, {
    x: 0.55, y: H - 0.285, w: 6, h: 0.22,
    fontSize: 8.5, color: C.textLight, fontFace: FONT, valign: 'middle',
  });
}

/* ---------- 箭头流程 ---------- */
function flow(slide, y, steps, opts = {}) {
  const { x0 = 0.7, totalW = 8.6, boxH = 0.62, gap = 0.42, colors = null } = opts;
  const n = steps.length;
  const boxW = (totalW - gap * (n - 1)) / n;
  const pal = colors || [C.blue, C.green, C.purple, C.amber, C.blue];
  steps.forEach((st, i) => {
    const bx = x0 + i * (boxW + gap);
    card(slide, { x: bx, y, w: boxW, h: boxH, fill: C.white, line: pal[i % pal.length] });
    slide.addShape('rect', { x: bx, y, w: boxW, h: 0.055, fill: { color: pal[i % pal.length] } });
    const main = typeof st === 'string' ? st : st.title;
    const sub = typeof st === 'string' ? '' : st.sub;
    slide.addText(main, {
      x: bx + 0.06, y: y + 0.08, w: boxW - 0.12, h: sub ? 0.3 : boxH - 0.14,
      fontSize: 11, bold: true, color: C.text, fontFace: FONT,
      align: 'center', valign: 'middle',
    });
    if (sub) {
      slide.addText(sub, {
        x: bx + 0.06, y: y + 0.36, w: boxW - 0.12, h: 0.24,
        fontSize: 8.5, color: C.textLight, fontFace: FONT,
        align: 'center', valign: 'middle',
      });
    }
    if (i < n - 1) {
      slide.addText('▶', {
        x: bx + boxW, y, w: gap, h: boxH,
        fontSize: 12, color: C.textLight, fontFace: FONT,
        align: 'center', valign: 'middle',
      });
    }
  });
}

module.exports = {
  C, FONT, W, H,
  blank, cover, titleBar, card, cardTitle, bullets, tag,
  statCard, table, noteBar, footer, flow,
};
