/**
 * 皮肤癌图像检测系统 —— 汇报PPT 生成脚本（16页，明亮医疗风）
 * 内容全部来自项目真实文档与实验数据
 */
const pptxgen = require('pptxgenjs');
const H = require('./helpers');
const { C, FONT, W } = H;

const OUT = process.env.OUT_FILE || '/mnt/d/Project/JXprojiect/Hermes-project/project/皮肤癌图像系统/交付文件/03.ppt/10-项目汇报.pptx';

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';
pres.author = '皮肤癌图像检测系统';
pres.title = '皮肤癌图像检测系统 - 项目汇报';

/* ================= P1 封面 ================= */
{
  const s = H.blank(pres);
  H.cover(s, {
    title: '皮肤癌图像检测系统',
    subtitle: '基于深度残差网络的皮肤病变良恶性判别 Web 应用',
    meta: ['AI应用开发', '图像分类', '医疗影像', '个人项目'],
  });
}

/* ================= P2 项目背景与意义 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '一、项目背景与意义', '为什么做这个项目', 2);
  H.footer(s);

  // 左：背景
  H.card(s, { x: 0.55, y: 1.22, w: 4.35, h: 3.42 });
  H.cardTitle(s, 0.75, 1.34, 3.9, '现实痛点', { icon: '◈' });
  H.bullets(s, 0.75, 1.7, 4.0, [
    '皮肤癌是最常见的癌症之一，早期筛查是提高治愈率的关键',
    '黑色素瘤恶性程度高、易转移，延误代价大',
    '有经验专家不足，限制大规模普查',
    { text: '现有同类网站多为泛分类科普介绍 + 医生付费在线问诊', bold: true, color: C.red },
    { text: '缺少可自主上传皮肤照片、直接给出良恶性结论的工具', bold: true, color: C.red },
  ], { gap: 0.42, size: 9.5 });
  H.noteBar(s, '传统皮肤镜诊断依赖专家，资源分布不均', { y: 3.9, fill: C.redLight, line: C.red, color: '991B1B' });

  // 右：意义 + 差异化
  H.card(s, { x: 5.1, y: 1.22, w: 4.35, h: 3.42 });
  H.cardTitle(s, 5.3, 1.34, 3.9, '项目价值与差异化', { icon: '◈' });
  const vals = [
    ['业务', '普及早期诊断意识，降低发病率与死亡率', C.blue],
    ['技术', '实践深度学习在 Web 环境的部署应用', C.green],
    ['社会', '缓解医疗资源不均，降低健康自检门槛', C.purple],
    ['完全免费', '无需注册付费，游客模式即可检测', C.amber],
    ['针对性强', '专攻皮肤病变良恶性，不做泛分类', C.amber],
    ['操作简单', '拖拽一张照片，秒级出结果与建议', C.amber],
  ];
  vals.forEach(([t, d, col], i) => {
    const y = 1.68 + i * 0.49;
    s.addShape('rect', { x: 5.3, y: y + 0.04, w: 0.055, h: 0.36, fill: { color: col } });
    s.addText(t, { x: 5.44, y, w: 1.15, h: 0.42, fontSize: 10.5, bold: true, color: col, fontFace: FONT, valign: 'middle' });
    s.addText(d, { x: 6.6, y, w: 2.6, h: 0.42, fontSize: 9, color: C.textSub, fontFace: FONT, valign: 'middle' });
  });
}

/* ================= P3 需求分析 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '二、需求分析', '任务书 6 大功能模块 + 2 项扩展', 3);
  H.footer(s);

  const mods = [
    ['图像上传', '拖拽/点击上传，多格式支持，实时预览', C.blue],
    ['图像预处理', '归一化、288×288 尺寸调整、格式转换', C.green],
    ['深度识别', '多模型集成二分类，良恶性判别，置信度输出', C.purple],
    ['结果展示', '可视化结果 + 健康建议 + 就医指导', C.amber],
    ['历史记录', '图像检测 / 问答双 Tab，筛选分页、CSV 导出', C.blue],
    ['用户管理', '注册、登录、个人信息管理', C.green],
    ['智能问答', '医疗知识库问答 + 结果解读，支持带图提问', C.teal],
    ['后台管理', '用户/记录管理、审计日志、模型监控', C.magenta],
  ];
  mods.forEach(([t, d, col], i) => {
    const col_i = i % 4, row_i = Math.floor(i / 4);
    const x = 0.55 + col_i * 2.32, y = 1.28 + row_i * 1.48;
    H.card(s, { x, y, w: 2.14, h: 1.32 });
    s.addShape('rect', { x, y, w: 2.14, h: 0.055, fill: { color: col } });
    s.addText(t, { x: x + 0.12, y: y + 0.13, w: 1.9, h: 0.28, fontSize: 11.5, bold: true, color: col, fontFace: FONT });
    s.addText(d, { x: x + 0.12, y: y + 0.45, w: 1.92, h: 0.78, fontSize: 8.2, color: C.textSub, fontFace: FONT, valign: 'top' });
  });

  H.noteBar(s, '非功能需求：推理延迟 < 500ms ｜ 主流浏览器兼容 ｜ 响应式适配 ｜ 医疗免责声明 ｜ 游客可用', { y: 4.42 });
}

/* ================= P4 系统架构 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '三、系统架构', '四层架构 · 前后端分离 + 双模型仲裁', 4);
  H.footer(s);

  // 四层架构
  const layers = [
    { t: '① 表现层　前端 Web 客户端', d: 'React 18 + Vite + TailwindCSS　｜　PC/移动端响应式　｜　6 个前台页面 + 9 个后台页面', c: C.blue, y: 1.22 },
    { t: '② 接口层　FastAPI 后端服务', d: '认证 / 检测 / 记录 / 问答 / 后台　｜　40 个 RESTful 接口 + 自动 API 文档', c: C.green, y: 2.12 },
    { t: '③ 推理层　双模型仲裁', d: '图像主判定：PyTorch GPU 集成（R101+ConvNeXt）｜ 类型参考：ONNX INT8（CPU）｜ 问答：Ollama 本地大模型', c: C.purple, y: 3.02 },
    { t: '④ 存储层　数据持久化', d: 'SQLite3（用户 / 检测记录 / 问答会话 / 审计日志）｜ 本地文件存储（上传图 + 模型权重）', c: C.amber, y: 3.92 },
  ];
  layers.forEach(({ t, d, c, y }) => {
    H.card(s, { x: 0.85, y, w: 8.3, h: 0.82, line: c });
    s.addShape('rect', { x: 0.85, y, w: 0.07, h: 0.82, fill: { color: c } });
    s.addText(t, { x: 1.1, y: y + 0.07, w: 7.9, h: 0.3, fontSize: 12, bold: true, color: c, fontFace: FONT });
    s.addText(d, { x: 1.1, y: y + 0.38, w: 7.9, h: 0.38, fontSize: 8.8, color: C.textSub, fontFace: FONT });
    if (y < 3.9) s.addText('▼', { x: 4.85, y: y + 0.82, w: 0.4, h: 0.08, fontSize: 9, color: C.textLight, fontFace: FONT, align: 'center' });
  });
  // 公网入口标注
  H.noteBar(s, '部署形态：生产模式前端由 FastAPI 托管，单进程单端口；对外通过 Cloudflare Tunnel 提供 HTTPS 加密公网访问', { y: 4.82, fill: C.greenLight, line: C.green, color: '065F46' });
}

/* ================= P5 技术栈选型 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '四、技术栈选型', '兼顾性能、开发效率与部署成本', 5);
  H.footer(s);

  H.table(s, 0.55, 1.2, 5.55, [
    ['层次', '技术选型', '版本'],
    ['深度学习', 'PyTorch + R101/ConvNeXt', '2.11.0+cu128'],
    ['模型部署', 'ONNX Runtime (INT8)', '1.30.0'],
    ['后端框架', 'FastAPI + Uvicorn', '0.141.1'],
    ['前端框架', 'React + Vite', '18.3 / 5.4'],
    ['UI 样式', 'TailwindCSS', '3.4'],
    ['数据存储', 'SQLite3 + 本地文件', '内置'],
    ['本地大模型', 'Ollama（医疗微调）', 'qwen3.5:4b'],
  ], {
    colW: [1.15, 2.7, 1.7],
    fontSize: 8.6,
    headH: 0.36,
    rowH: 0.46,
  });

  // 右侧：技术优化线（文字加大 + 间距拉开填满卡片）
  H.card(s, { x: 6.28, y: 1.2, w: 3.17, h: 3.58, line: C.green });
  H.cardTitle(s, 6.44, 1.3, 2.9, '技术优化线', { icon: '⚙', color: C.green });
  const opts = [
    ['数据混合', 'CutMix/MixUp 抑制过拟合，裂口 -17.96% → -9.01%', C.blue],
    ['模型集成', '多架构概率平均，AUC 突破单模型天花板 0.919 → 0.9276', C.purple],
    ['阈值标定', '三档工作模式，准确率与恶性召回按场景权衡', C.amber],
    ['量化压缩', 'INT8 静态量化，体积压缩 3.93x，精度仅 -0.47%', C.teal],
  ];
  opts.forEach(([t, d, col], i) => {
    const y = 1.62 + i * 0.93;
    s.addShape('rect', { x: 6.42, y: y + 0.03, w: 0.07, h: 0.82, fill: { color: col } });
    s.addText(t, { x: 6.60, y, w: 2.72, h: 0.36, fontSize: 14, bold: true, color: col, fontFace: FONT });
    s.addText(d, { x: 6.60, y: y + 0.35, w: 2.74, h: 0.60, fontSize: 11, color: C.textSub, fontFace: FONT, valign: 'top', lineSpacingMultiple: 1.15 });
  });

  H.noteBar(s, '三原则：低学习成本 / 快速 MVP / 低成本　▸　所有选型均可本地跑通，不依赖付费云服务', { y: 4.9 });
}

/* ================= P6 算法流程 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '五、算法流程', '从数据到部署的四个阶段', 6);
  H.footer(s);

  H.flow(s, 1.28, [
    { title: '数据准备', sub: 'HAM + BCN 双数据集' },
    { title: '模型训练', sub: '迁移学习 + CutMix' },
    { title: '模型优化', sub: '集成 + 阈值 + 量化' },
    { title: '推理部署', sub: 'FastAPI + 公网隧道' },
  ]);

  const details = [
    ['① 数据准备', ['HAM10000 + BCN20000 双数据集', '混训集 22428 张', '病灶级划分（防数据泄漏）'], C.blue],
    ['② 模型训练', ['ResNet101 + ConvNeXt 迁移学习', 'CutMix 数据混合 + 差分学习率', 'AMP 混合精度 + 早停'], C.green],
    ['③ 模型优化', ['多架构集成搜索', '阈值扫描（61 个操作点）', 'ONNX INT8 量化，压缩 3.93 倍'], C.purple],
    ['④ 推理部署', ['Predictor 单例自动加载', 'FastAPI 提供 40 个 REST 接口', 'Cloudflare Tunnel 公网 HTTPS'], C.amber],
  ];
  details.forEach(([t, items, col], i) => {
    const x = 0.55 + i * 2.28;
    H.card(s, { x, y: 2.28, w: 2.1, h: 2.15 });
    s.addShape('rect', { x, y: 2.28, w: 2.1, h: 0.055, fill: { color: col } });
    s.addText(t, { x: x + 0.12, y: 2.4, w: 1.86, h: 0.28, fontSize: 10.5, bold: true, color: col, fontFace: FONT });
    items.forEach((it, j) => {
      s.addText('• ' + it, {
        x: x + 0.12, y: 2.75 + j * 0.42, w: 1.86, h: 0.42,
        fontSize: 8.5, color: C.textSub, fontFace: FONT, valign: 'top',
      });
    });
  });

  H.noteBar(s, '核心原则：推理预处理必须与训练时完全一致，否则精度大幅下降', { y: 4.58 });
}

/* ================= P7 公网部署上线 ★新增 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '六、公网部署上线', 'Cloudflare Tunnel · 免安装免公网 IP 的加密公网访问', 7);
  H.footer(s);

  // 左：部署链路（五段）
  H.card(s, { x: 0.55, y: 1.22, w: 5.35, h: 3.35 });
  H.cardTitle(s, 0.72, 1.32, 5.0, '部署链路（五段）', { icon: '▸' });
  const chain = [
    ['① 用户访问', '浏览器打开 skin.osanu.dpdns.org/app/', C.blue],
    ['② Cloudflare 边缘', '全球 DNS 解析 + HTTPS 自动加密（无需自签证书）', C.blue],
    ['③ 加密隧道', 'cloudflared 主动外连，无需公网 IP / 端口映射', C.green],
    ['④ WSL 本机', '隧道落到 localhost:8000 的 FastAPI 服务', C.green],
    ['⑤ 一键起停', 'start.sh 内置隧道幂等段，随服务自动拉起', C.purple],
  ];
  chain.forEach(([t, d, col], i) => {
    const y = 1.7 + i * 0.56;
    s.addShape('rect', { x: 0.72, y: y + 0.02, w: 0.055, h: 0.46, fill: { color: col } });
    s.addText(t, { x: 0.86, y, w: 1.5, h: 0.5, fontSize: 9.5, bold: true, color: col, fontFace: FONT, valign: 'middle' });
    s.addText(d, { x: 2.32, y, w: 3.4, h: 0.5, fontSize: 8.4, color: C.textSub, fontFace: FONT, valign: 'middle' });
  });

  // 右：部署亮点
  H.card(s, { x: 6.1, y: 1.22, w: 3.35, h: 3.35, fill: C.greenLight, line: C.green });
  H.cardTitle(s, 6.26, 1.32, 3.05, '部署亮点', { icon: '✓', color: '065F46' });
  H.bullets(s, 6.26, 1.72, 3.05, [
    { text: '免安装免公网 IP', bold: true },
    '同学、老师扫码即用，不必同一 WiFi',
    { text: '一条隧道挂多项目', bold: true },
    '皮肤癌(8000) + 医小喵(8001) 复用同一隧道',
    { text: 'HTTPS 加密', bold: true },
    '浏览器绿锁，医疗数据不裸传',
    { text: '幂等自愈 · 零成本', bold: true },
    '服务重启自动重连；Cloudflare 免费版，无服务器无备案',
  ], { gap: 0.33, size: 8.2, lineColor: C.green });

  H.noteBar(s, '已上线：https://skin.osanu.dpdns.org/app/ ｜ 后台 /admin/ ｜ API 文档 /docs —— 由 Cloudflare Tunnel 提供公网加密访问',
    { y: 4.7, fill: C.greenLight, line: C.green, color: '065F46' });
}

/* ================= P8 数据工程 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '七、数据工程', 'HAM10000 + BCN20000 双数据集 · 防泄漏设计', 8);
  H.footer(s);

  // 数据规模（双数据集）
  H.statCard(s, 0.55, 1.24, 2.1, 1.0, '10015', 'HAM10000 皮肤镜', { accent: C.blue, vsize: 19 });
  H.statCard(s, 2.75, 1.24, 2.1, 1.0, '12413', 'BCN20000（ISIC）', { accent: C.orange || C.amber, vsize: 19 });
  H.statCard(s, 4.95, 1.24, 2.1, 1.0, '22428', '混训数据集', { accent: C.purple, vsize: 19 });
  H.statCard(s, 7.15, 1.24, 2.3, 1.0, '2539', 'BCN 跨域测试集', { accent: C.teal, vsize: 19 });

  // 类别映射表
  H.card(s, { x: 0.55, y: 2.42, w: 4.35, h: 1.72 });
  H.cardTitle(s, 0.72, 2.5, 4.0, '7 类 → 2 类映射', { icon: '▸' });
  H.table(s, 0.72, 2.82, 4.0, [
    ['原始类别', '归类', '图片数'],
    ['mel / bcc / akiec', '恶性', '1954'],
    ['nv / bkl / df / vasc', '良性', '8061'],
  ], { colW: [2.2, 0.8, 1.0], fontSize: 8.5, headH: 0.28, rowH: 0.28 });

  // 防泄漏
  H.card(s, { x: 5.1, y: 2.42, w: 4.35, h: 1.72, fill: C.blueSoft, line: C.borderBlue });
  H.cardTitle(s, 5.27, 2.5, 4.0, '关键设计：病灶级划分', { icon: '▸' });
  H.bullets(s, 5.27, 2.82, 4.0, [
    { text: '同一 lesion_id 的图片不跨集', bold: true },
    '病灶级交集 = 0 ✓　图片级交集 = 0 ✓',
  ], { gap: 0.32, size: 9 });

  H.noteBar(s, '双数据集：HAM10000（维也纳，7 类）+ BCN20000（巴塞罗那，9 类，含低色素难样本）→ 病灶级划分 + ISIC S3 官方直链下载', { y: 4.35, fill: C.greenLight, line: C.green, color: '065F46' });
}

/* ================= P8 模型训练实验 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '八、模型训练实验', '十一轮对比实验，定位性能瓶颈', 9);
  H.footer(s);

  H.table(s, 0.55, 1.16, 8.9, [
    ['#', '实验', '训练数据', '关键策略', '准确率', 'AUC'],
    ['1', '基线', '792张', 'medium增强', '81.69%', '0.8552'],
    ['2', '方案A', '792张', 'strong增强+保守lr', '81.69%', '0.8605'],
    ['3', '实验C', '3672张', '1:1平衡+超低lr', '80.75%', '0.8901'],
    ['4', '方案D', '9802张', 'warmup+标签平滑', '83.57%', '0.9146'],
    ['5', 'v2全量', '9802张', '数据扩容', '84.98%', '0.9162'],
    ['6', '方案E', '9802张', 'R101+288分辨率', '84.98%', '0.9187'],
    ['7', 'TTA评测', '9802张', '测试时增强（未采用）', '83.57%', '0.9242'],
    ['8', 'CutMix', '9476张', 'CutMix+长训练50轮', '85.92%', '0.9207'],
    ['9', '集成v1', '9802张', 'R50+R101概率平均', '85.45%', '0.9287'],
    ['10', '集成v2', '9476张', 'R101×2+ConvNeXt', '85.45%', '0.9242'],
    ['11', '集成v3 ★', '9476张', 'R101+CutMix等权', '86.38%', '0.9276'],
  ], {
    colW: [0.55, 1.25, 1.2, 2.9, 1.5, 1.5],
    fontSize: 8.2, headH: 0.28, rowH: 0.30, highlightRow: 11,
  });

  H.noteBar(s, '关键发现：数据量是最大瓶颈（792→9802张，AUC +6.1%）｜ CutMix 治过拟合（裂口 -17.96%→-9.01%）｜ 集成突破单模型天花板至 AUC 0.9276', { y: 4.68 });
}

/* ================= P9 训练问题诊断 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '九、训练问题诊断', '从曲线与指标中发现并解决问题', 10);
  H.footer(s);

  const probs = [
    {
      t: '问题一：严重过拟合',
      d: '训练98% / 测试79%，差距19.5%',
      sol: '强增强 + 保守学习率 + 权重衰减',
      res: '差距降至 8%',
      col: C.red,
    },
    {
      t: '问题二：最佳出现在 epoch 1',
      d: '学习率过大，一轮即破坏预训练特征',
      sol: 'Warmup 渐进（起始 lr = 目标/50）',
      res: '曲线转为稳步上升',
      col: C.amber,
    },
    {
      t: '问题三：模型学不动',
      d: 'lr 降至 2e-6 后过拟合消失但准确率卡在 80%',
      sol: '差分学习率 + 适中 lr（5e-5）',
      res: '准确率恢复至 84.98%',
      col: C.purple,
    },
  ];
  probs.forEach((p, i) => {
    const y = 1.3 + i * 1.15;
    H.card(s, { x: 0.55, y, w: 8.9, h: 1.0, line: p.col });
    s.addShape('rect', { x: 0.55, y, w: 0.07, h: 1.0, fill: { color: p.col } });
    s.addText(p.t, { x: 0.78, y: y + 0.08, w: 3.5, h: 0.3, fontSize: 11.5, bold: true, color: p.col, fontFace: FONT });
    s.addText(p.d, { x: 0.78, y: y + 0.38, w: 3.6, h: 0.5, fontSize: 9, color: C.textSub, fontFace: FONT, valign: 'top' });
    s.addText('解决：' + p.sol, { x: 4.6, y: y + 0.1, w: 4.6, h: 0.35, fontSize: 9.5, color: C.text, fontFace: FONT });
    s.addText('效果：' + p.res, { x: 4.6, y: y + 0.5, w: 4.6, h: 0.35, fontSize: 9.5, bold: true, color: C.green, fontFace: FONT });
  });

  H.noteBar(s, '训练曲线（epoch1即最佳）是判断"学习率过大"的关键信号', { y: 4.85 });
}

/* ================= P10 模型集成 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '十、模型集成', '零训练成本，突破单模型 AUC 天花板', 11);
  H.footer(s);

  // 集成方案
  H.card(s, { x: 0.55, y: 1.24, w: 4.35, h: 1.42 });
  H.cardTitle(s, 0.72, 1.33, 4.0, '集成方案', { icon: '▸' });
  H.bullets(s, 0.72, 1.64, 4.0, [
    { text: '成员：ResNet101/288 + ConvNeXt-T/288 (CutMix)', bold: true },
    '融合：softmax 概率逐元素平均（等权）',
    '推荐阈值：0.48（验证集标定，61 点扫描）',
  ], { gap: 0.30, size: 8.8 });

  // 效果对比
  H.card(s, { x: 5.1, y: 1.24, w: 4.35, h: 1.42, fill: C.blueSoft, line: C.borderBlue });
  H.cardTitle(s, 5.27, 1.33, 4.0, '效果对比', { icon: '✓', color: C.blueDeep });
  s.addText('CutMix 单模型   acc 85.92%  AUC 0.9207', {
    x: 5.27, y: 1.64, w: 4.0, h: 0.28, fontSize: 9, color: C.textSub, fontFace: FONT });
  s.addText('★ 集成              acc 86.38%  AUC 0.9276', {
    x: 5.27, y: 1.94, w: 4.0, h: 0.28, fontSize: 10.5, bold: true, color: C.blueDeep, fontFace: FONT });
  s.addText('准确率 +0.46 / 恶性召回 +4.24 个百分点', {
    x: 5.27, y: 2.26, w: 4.0, h: 0.3, fontSize: 9, color: '065F46', fontFace: FONT });

  // 关键发现（最重要）
  H.card(s, { x: 0.55, y: 2.8, w: 5.55, h: 1.62, fill: C.amberLight, line: C.amber });
  H.cardTitle(s, 0.75, 2.88, 5.2, '关键发现：集成必须重定阈值', { icon: '★', color: '92400E' });
  s.addText('概率平均后分布更集中，旧的 0.5 不再是最优分割点。任何改变输出分布的改动——集成、蒸馏、重训练、数据混合——都必须重新校准决策阈值。', {
    x: 0.78, y: 3.2, w: 5.2, h: 0.62, fontSize: 8.6, color: '92400E', fontFace: FONT, valign: 'top' });
  s.addText('TTA 在本场景有害：皮肤镜图像具方向性，翻转/旋转破坏解剖方位感。', {
    x: 0.78, y: 3.86, w: 5.2, h: 0.46, fontSize: 8.6, color: '991B1B', fontFace: FONT, valign: 'top' });

  // 右侧：置信区间与分歧度
  H.card(s, { x: 6.28, y: 2.8, w: 3.17, h: 1.62, fill: C.tealLight, line: C.teal });
  H.cardTitle(s, 6.44, 2.88, 2.9, '置信区间与分歧度', { icon: '◎', color: '0F766E' });
  H.bullets(s, 6.44, 3.2, 2.9, [
    '输出为概率值（0~1），界面以置信度展示',
    '两成员平均分歧 5.8%；>15% 标记「建议复检」',
    '阈值 0.48 附近（0.40~0.56）为不确定带',
  ], { gap: 0.38, size: 8.2, lineColor: C.teal });
}

/* ================= P11 七类病变类型分类 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '十一、七类病变类型分类（辅助参考）', '在主结论之外，提供病变类型参考信息', 12);
  H.footer(s);

  // 定位说明
  H.card(s, { x: 0.55, y: 1.28, w: 8.9, h: 0.72, fill: C.blueSoft, line: C.borderBlue });
  s.addText('功能定位：主结论（良性/恶性，acc 86.38%）是核心判断；类型判断（7 类，acc 74.32%）仅作参考，界面明确标注不可作为诊断依据',
    { x: 0.75, y: 1.28, w: 8.6, h: 0.72, fontSize: 9.5, color: C.blueDeep, fontFace: FONT, valign: 'middle' });

  // 四大指标
  H.statCard(s, 0.55, 2.1, 2.1, 1.0, '74.32%', '准确率', { accent: C.blue });
  H.statCard(s, 2.75, 2.1, 2.1, 1.0, '0.9258', 'AUC (macro)', { accent: C.green });
  H.statCard(s, 4.95, 2.1, 2.1, 1.0, '9832', '训练图片（硬链接）', { accent: C.purple });
  H.statCard(s, 7.15, 2.3, 2.3, 1.0, '0', '额外磁盘占用', { accent: C.amber });

  // 类别表现
  H.card(s, { x: 0.55, y: 3.28, w: 4.35, h: 1.32 });
  H.cardTitle(s, 0.72, 3.36, 4.0, '表现较好的类别', { icon: '✓', color: C.green });
  H.bullets(s, 0.72, 3.68, 4.0, [
    'nv（痣）F1 0.865 ⭐  样本最多',
    'vasc（血管性）F1 0.857  召回 100%',
    'bcc（基底细胞癌）F1 0.778  关键恶性类',
  ], { gap: 0.3, size: 9, lineColor: C.green });

  H.card(s, { x: 5.1, y: 3.28, w: 4.35, h: 1.32, fill: 'FFFBF5', line: C.amber });
  H.cardTitle(s, 5.27, 3.36, 4.0, '主要问题', { icon: '▲', color: '92400E' });
  H.bullets(s, 5.27, 3.68, 4.0, [
    'nv ↔ bkl/mel 互相混淆（诊断名相似）',
    'df 训练样本仅 115 张，精确率偏低',
    'AUC 0.9258 高但 acc 低 → 瓶颈是样本量',
  ], { gap: 0.3, size: 9, lineColor: C.amber });

  H.noteBar(s, '来源：训练数据的原始 7 类标注（本质是良恶性标签的细分特征）｜ 联动本地医疗大模型输出该类别的具体处置建议', { y: 4.72, fill: C.tealLight, line: C.teal, color: '0F766E' });
}

/* ================= P12 模型优化：阈值调优 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '十二、模型优化（一）：阈值调优', '医疗场景下"宁可误报不可漏诊"', 13);
  H.footer(s);

  H.table(s, 0.55, 1.3, 8.9, [
    ['工作模式', '阈值', '准确率', '恶性召回', '漏诊率', '适用场景'],
    ['筛查模式', '0.20', '78.87%', '99.15%', '0.85%', '初步筛查（不漏诊）'],
    ['平衡模式', '0.33', '83.10%', '95.76%', '4.24%', '日常自检'],
    ['精确模式（默认）', '0.48', '86.38%', '91.53%', '8.47%', '准确率优先'],
  ], {
    colW: [2.0, 0.9, 1.3, 1.5, 1.3, 1.9],
    fontSize: 10, headH: 0.36, rowH: 0.44, highlightRow: 1,
  });

  // 实例证据
  H.card(s, { x: 0.55, y: 3.1, w: 8.9, h: 1.35, fill: C.greenLight, line: C.green });
  H.cardTitle(s, 0.75, 3.2, 8.5, '实测证据：阈值确实改变判定结果', { icon: '✓', color: '065F46' });
  s.addText(
    '筛查模式下 213 张测试集仅漏诊 1 张（恶性召回 99.15%），代价是误报增至 44 张；阈值扫描范围 0.20~0.80，共 61 个操作点，脚本可复现',
    { x: 0.78, y: 3.55, w: 8.5, h: 0.32, fontSize: 10, color: '065F46', fontFace: FONT, valign: 'middle' }
  );
  s.addText(
    '→ 筛查模式用 1.41% 的准确率代价，换取漏诊率从 12.71% 降至 3.39%（降低 73%）',
    { x: 0.78, y: 3.9, w: 8.5, h: 0.32, fontSize: 10, bold: true, color: '065F46', fontFace: FONT, valign: 'middle' }
  );

  H.noteBar(s, '阈值扫描范围 0.20~0.80，共 61 个操作点，脚本可复现（集成与单模型分别扫描）', { y: 4.68 });
}

/* ================= P13 模型优化：量化压缩 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '十三、模型优化（二）：量化压缩', '两个模型均压缩 3.93 倍，精度损失 <1%', 14);
  H.footer(s);

  // 四大指标
  H.statCard(s, 0.55, 1.3, 2.1, 1.1, '3.93x', '体积压缩比（两个模型）', { accent: C.blue });
  H.statCard(s, 2.75, 1.3, 2.1, 1.1, '22.9MB', '单个模型体积', { accent: C.green });
  H.statCard(s, 4.95, 1.3, 2.1, 1.1, '6.5x', '7类加载加速', { accent: C.purple });
  H.statCard(s, 7.15, 1.3, 2.3, 1.1, '21x', '主模型加载加速', { accent: C.amber });

  // 对比表（含7类）
  H.table(s, 0.55, 2.6, 5.5, [
    ['模型 / 方案', '体积', '延迟', '准确率'],
    ['主分类 PyTorch', '90.0MB', '34.1ms', '84.98%'],
    ['主分类 ONNX INT8', '22.9MB', '24.0ms', '84.51%'],
    ['7类 PyTorch', '90.0MB', '17.6ms', '73.77%'],
    ['7类 ONNX INT8', '22.9MB', '25.6ms', '70.49%'],
  ], { colW: [1.95, 1.05, 1.15, 1.35], fontSize: 9, headH: 0.3, rowH: 0.32, highlightRow: 4 });

  // 技术路线
  H.card(s, { x: 6.25, y: 2.6, w: 3.2, h: 1.9 });
  H.cardTitle(s, 6.4, 2.7, 2.9, '技术路线', { icon: '▸' });
  s.addText('PyTorch FP32\n   ↓ 导出 ONNX\nONNX FP32\n   ↓ INT8 静态量化\nONNX INT8 (QDQ)', {
    x: 6.4, y: 3.02, w: 2.9, h: 1.35,
    fontSize: 9.5, color: C.textSub, fontFace: FONT, valign: 'top', lineSpacingMultiple: 1.35,
  });

  H.noteBar(s, 'PyTorch 原生量化受限于缺 fbgemm 算子，改用工业界标准的 ONNX Runtime 路径；两个模型均部署 ONNX INT8', { y: 4.68 });
}

/* ================= P14 系统功能演示 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '十四、系统功能', '导航空器 8 大模块，覆盖检测 / 问答 / 管理全链路', 15);
  H.footer(s);

  const pages = [
    ['首页', ['模型状态实时展示', '六大功能卡片', '检测流程动画演示'], C.blue],
    ['图像检测 ★', ['拖拽上传 + 实时预览', '三档工作模式切换', '部位先验 + 结果建议'], C.green],
    ['模型解释', ['Grad-CAM 热力图', '关注区域可视化', '集成成员一致性对比'], C.purple],
    ['智能问答', ['医疗知识库问答', '支持带图提问', '检测结果解读辅助'], C.teal],
    ['检测历史', ['图像 / 问答双 Tab', '气泡式对话详情', '筛选分页 + CSV 导出'], C.blue],
    ['后台管理', ['9 个页面：看板/用户/记录', '审计日志 / 模型管理', '系统状态监控'], C.magenta],
    ['登录 / 注册', ['JWT 认证 + 角色权限', 'PBKDF2 12 万次哈希', '游客模式可直接检测'], C.amber],
    ['公网部署', ['Cloudflare Tunnel', '免安装、扫码即用', 'HTTPS 加密访问'], C.green],
  ];
  pages.forEach(([t, items, col], i) => {
    const colI = i % 4, rowI = Math.floor(i / 4);
    const x = 0.55 + colI * 2.32, y = 1.26 + rowI * 1.72;
    H.card(s, { x, y, w: 2.14, h: 1.58 });
    s.addShape('rect', { x, y, w: 2.14, h: 0.4, fill: { color: col } });
    s.addText(t, { x: x + 0.08, y, w: 1.98, h: 0.4, fontSize: 10, bold: true, color: C.white, fontFace: FONT, align: 'center', valign: 'middle' });
    items.forEach((it, j) => {
      s.addText('• ' + it, { x: x + 0.1, y: y + 0.47 + j * 0.36, w: 1.94, h: 0.34, fontSize: 7.6, color: C.textSub, fontFace: FONT, valign: 'top' });
    });
  });

  // 亮点
  H.card(s, { x: 0.55, y: 4.68, w: 8.9, h: 0.5, fill: C.blueSoft, line: C.borderBlue });
  s.addText('界面亮点：响应式三断点适配 ｜ 结果双重编码（颜色+图标+文字）｜ 医疗免责声明三处展示 ｜ 扫描线动画反馈 ｜ 全站中英双语卡片',
    { x: 0.75, y: 4.68, w: 8.6, h: 0.5, fontSize: 8.8, color: C.blueDeep, fontFace: FONT, valign: 'middle' });
}

/* ================= P15 测试结果 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '十五、测试结果', '31 个测试用例 100% 通过', 16);
  H.footer(s);

  H.statCard(s, 0.55, 1.3, 1.75, 1.1, '22/22', '前台接口测试', { accent: C.blue });
  H.statCard(s, 2.45, 1.3, 1.75, 1.1, '9/9', '边界异常测试', { accent: C.green });
  H.statCard(s, 4.35, 1.3, 1.75, 1.1, '100%', '测试通过率', { accent: C.purple });
  H.statCard(s, 6.25, 1.3, 1.0, 1.1, '24', 'QPS', { accent: C.amber });
  H.statCard(s, 7.4, 1.3, 2.05, 1.1, '65ms', '单张推理(GPU)', { accent: C.blue });

  // 安全性测试
  H.card(s, { x: 0.55, y: 2.6, w: 4.35, h: 1.85 });
  H.cardTitle(s, 0.72, 2.7, 4.0, '安全性验证', { icon: '▸' });
  H.bullets(s, 0.72, 3.05, 4.0, [
    '路径穿越攻击 → 拦截（404）',
    '越权访问他人记录 → 拦截',
    '非法文件格式 / 超大文件 → 拒绝',
    '无 token 访问受保护接口 → 401',
  ], { gap: 0.34, size: 9 });

  // 模型指标
  H.card(s, { x: 5.1, y: 2.6, w: 4.35, h: 1.85 });
  H.cardTitle(s, 5.27, 2.7, 4.0, '模型性能指标', { icon: '▸' });
  H.bullets(s, 5.27, 3.05, 4.0, [
    { text: '集成主模型 acc 86.38% / AUC 0.9276', bold: true },
    '7类参考 acc 74.32% / AUC 0.9258',
    '筛查模式恶性召回 99.15%（漏诊仅 1 张）',
    { text: '单 worker 串行化，稳定性优先', bold: false },
  ], { gap: 0.34, size: 9 });

  H.noteBar(s, '测试脚本可复现：scripts/system_test.py（输出 JSON 原始数据留档）', { y: 4.62 });
}

/* ================= P16 技术难点与应对 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '十六、技术难点与应对', '四个关键问题的定位与解决', 17);
  H.footer(s);

  const diffs = [
    ['数据泄漏风险', '同一病灶多张图若跨集划分，模型"考前见过题"', '病灶级划分，交集强制为 0', C.red],
    ['训练 GPU 饿死', '从 /mnt/d 读图慢，dataloader 供不上数据', '数据移至本地盘，读速提升 8 倍', C.amber],
    ['PyTorch 量化受限', '缺 fbgemm 算子，剪枝不省空间', '改用 ONNX Runtime INT8 量化', C.purple],
    ['准确率未达 90%', '测试集仅 213 张，数据信息量到顶', '多维指标呈现 + 阈值调优补偿', C.blue],
  ];
  diffs.forEach(([t, p, sol, col], i) => {
    const y = 1.3 + i * 0.92;
    H.card(s, { x: 0.55, y, w: 8.9, h: 0.8, line: col });
    s.addShape('rect', { x: 0.55, y, w: 0.07, h: 0.8, fill: { color: col } });
    s.addText(t, { x: 0.78, y: y + 0.06, w: 2.5, h: 0.3, fontSize: 11, bold: true, color: col, fontFace: FONT });
    s.addText(p, { x: 0.78, y: y + 0.38, w: 3.6, h: 0.34, fontSize: 8.5, color: C.textSub, fontFace: FONT });
    s.addText('▸ 应对：' + sol, { x: 4.6, y: y + 0.05, w: 4.7, h: 0.7, fontSize: 9.5, color: C.text, fontFace: FONT, valign: 'middle' });
  });
}

/* ================= P17 不足与改进 ================= */
{
  const s = H.blank(pres);
  H.titleBar(s, '十七、不足与改进方向', '诚实呈现问题，规划优化路径', 18);
  H.footer(s);

  // 不足
  H.card(s, { x: 0.55, y: 1.3, w: 4.35, h: 3.3, fill: 'FFFBF5', line: C.amber });
  H.cardTitle(s, 0.75, 1.42, 4.0, '当前不足', { icon: '▲', color: '92400E' });
  const cons = [
    ['准确率 86.38% < 90%', '测试集仅 213 张，每错 1 张 = 0.47%'],
    ['7 类类型准确率仅 74.32%', '少数类样本少（df 仅 115 张）'],
    ['推理依赖 GPU 才能达 65ms', '无 GPU 时回退 CPU，约 1~2 秒/张'],
    ['公网 HTTPS / 生产加固', '原为本地演示，无对外访问能力'],
  ];
  cons.forEach(([t, d], i) => {
    const y = 1.85 + i * 0.66;
    s.addText('• ' + t, { x: 0.75, y, w: 3.95, h: 0.28, fontSize: 10, bold: true, color: '92400E', fontFace: FONT });
    s.addText('   ' + d, { x: 0.75, y: y + 0.28, w: 3.95, h: 0.3, fontSize: 8.5, color: C.textSub, fontFace: FONT });
  });

  // 改进
  H.card(s, { x: 5.1, y: 1.3, w: 4.35, h: 3.3, fill: C.blueSoft, line: C.borderBlue });
  H.cardTitle(s, 5.3, 1.42, 4.0, '改进方向', { icon: '✓', color: C.blueDeep });
  const pros = [
    ['扩充数据 + 跨域验证', '混训集 22428 张已就绪，BCN 跨域已验证'],
    ['七类参考 + 可解释性', 'Grad-CAM 热力图已上线'],
    ['ONNX INT8 兜底', '量化模型 22.9MB，CPU 可跑'],
    ['✅ 已完成：Cloudflare Tunnel', 'skin.osanu.dpdns.org 加密公网访问'],
  ];
  pros.forEach(([t, d], i) => {
    const y = 1.85 + i * 0.66;
    s.addText('• ' + t, { x: 5.3, y, w: 3.95, h: 0.28, fontSize: 10, bold: true, color: C.blueDeep, fontFace: FONT });
    s.addText('   ' + d, { x: 5.3, y: y + 0.28, w: 3.95, h: 0.3, fontSize: 8.5, color: C.textSub, fontFace: FONT });
  });
}

/* ================= P18 感谢聆听（收尾页）================= */
{
  const s = H.blank(pres);
  s.background = { color: C.white };
  s.addShape('rect', { x: 0, y: 0, w: W, h: 0.12, fill: { color: C.blue } });
  s.addShape('rect', { x: 0, y: 5.505, w: W, h: 0.12, fill: { color: C.blue } });

  // 左上/右上装饰
  s.addShape('ellipse', { x: 8.55, y: 0.5, w: 0.9, h: 0.9, fill: { color: C.blueLight }, line: { color: C.blueLight } });
  s.addShape('rect', { x: 0.7, y: 0.72, w: 0.075, h: 1.75, fill: { color: C.blue } });

  // 主视觉：感谢聆听
  s.addText('18 / THANK YOU', {
    x: 0.9, y: 1.42, w: 8.2, h: 0.3,
    fontSize: 12, bold: true, color: C.blue, fontFace: FONT, align: 'center', charSpacing: 3,
  });
  s.addText('感谢聆听', {
    x: 0.9, y: 1.85, w: 8.2, h: 1.05,
    fontSize: 52, bold: true, color: C.text, fontFace: FONT, align: 'center', valign: 'middle',
  });
  s.addText('敬 请 指 正', {
    x: 0.9, y: 2.98, w: 8.2, h: 0.48,
    fontSize: 19, bold: true, color: C.blue, fontFace: FONT, align: 'center', valign: 'middle',
  });
  // 分隔线
  s.addShape('rect', { x: 4.55, y: 3.62, w: 0.9, h: 0.055, fill: { color: C.amber } });

  // 三个核心数字
  const keys = [
    ['86.38%', '集成准确率', C.amber],
    ['0.9276', '集成 AUC', C.blue],
    ['40', 'RESTful 接口', C.purple],
  ];
  keys.forEach(([v, l, col], i) => {
    const x = 1.55 + i * 2.4;
    s.addText(v, { x, y: 3.95, w: 2.2, h: 0.5, fontSize: 24, bold: true, color: col, fontFace: FONT, align: 'center', valign: 'middle' });
    s.addText(l, { x, y: 4.44, w: 2.2, h: 0.28, fontSize: 10, color: C.textSub, fontFace: FONT, align: 'center', valign: 'middle' });
  });

  // 底部信息条
  H.noteBar(s, '皮肤癌图像检测系统　2027 届数据科学 · 阶段项目汇报　｜　公网演示：skin.osanu.dpdns.org/app/',
    { y: 4.88, fill: C.blueSoft, line: C.borderBlue, color: C.blueDeep });
}

pres.writeFile({ fileName: OUT }).then(() => {
  console.log('✅ 生成成功: ' + OUT);
});
