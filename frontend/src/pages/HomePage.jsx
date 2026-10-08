import { Link } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { healthApi } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import FeatureCarousel from '../components/FeatureCarousel'
import ProcessShowcase from '../components/ProcessShowcase'
import HeroPlane from '../components/HeroPlane'

export default function HomePage() {
  const { user, stats } = useAuth()
  const [health, setHealth] = useState(null)
  const [chatSt, setChatSt] = useState(null)
  const heroRef = useRef(null)
  const [heroProg, setHeroProg] = useState(0)

  useEffect(() => {
    healthApi.check().then(setHealth).catch(() => setHealth(null))
    healthApi.chatStatus().then(setChatSt).catch(() => setChatSt(null))
  }, [])

  // hero 滚动进度 0→1：滚过约 0.85 屏时完成（文字合并、内容淡出、飞机飞离）
  useEffect(() => {
    let raf = 0
    const onScroll = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const vh = window.innerHeight || 900
        const p = Math.min(1, Math.max(0, (window.scrollY || 0) / (vh * 0.85)))
        setHeroProg(p)
      })
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [])

  // 精确计算两行合并所需的位移量（响应式：任何视口都对齐，不靠魔法百分比）
  // 目标：A(洞察入微) 与 B(防患未然) 并排成一行 "洞察入微 防患未然"、水平居中
  useEffect(() => {
    const measure = () => {
      const sec = heroRef.current
      if (!sec) return
      const a = sec.querySelector('.hero-line-a')
      const b = sec.querySelector('.hero-line-b')
      if (!a || !b) return
      // ⚠️ 必须在 prog=0 的基准态下测量：否则用户已滚动时量到的是位移后的位置，
      //    位移量会被反复叠加放大。这里临时归零、量完恢复。
      const saved = sec.style.getPropertyValue('--hero-prog')
      sec.style.setProperty('--hero-prog', '0')
      const secRect = sec.getBoundingClientRect()
      const ra = a.getBoundingClientRect()
      const rb = b.getBoundingClientRect()
      const wa = ra.width
      const wb = rb.width
      const fs = parseFloat(getComputedStyle(a).fontSize) || 64
      const gap = Math.round(fs * 0.24)         // 两行之间的间隔
      const total = wa + gap + wb
      // 合并后整句的起始 x（hero 内容区水平居中）
      const startX = secRect.left + (secRect.width - total) / 2
      // A：从当前左边缘移到 startX
      const ax = Math.round(startX - ra.left)
      // B：从当前左边缘移到 startX + wa + gap
      const bx = Math.round(startX + wa + gap - rb.left)
      sec.style.setProperty('--shift-ax', ax + 'px')
      sec.style.setProperty('--shift-bx', bx + 'px')
      if (saved) sec.style.setProperty('--hero-prog', saved)
      else sec.style.removeProperty('--hero-prog')
    }
    measure()
    const ro = new ResizeObserver(measure)
    if (heroRef.current) ro.observe(heroRef.current)
    window.addEventListener('resize', measure)
    // 字体加载完成后宽度会变，重新量一次
    if (document.fonts?.ready) document.fonts.ready.then(measure).catch(() => {})
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [])

  // 检测流程四步（文案含项目真实参数，供右侧动画配合展示）
  const processSteps = [
    {
      title: '上传图像',
      desc: '拍摄或选取清晰的皮肤病变部位照片，拖拽或点击上传。支持 JPG / PNG / BMP / WEBP，单张不超过 10MB，上传后可即时预览并补充部位、发现时间等备注。',
      stage: 'Step 01 · Upload',
    },
    {
      title: '图像预处理',
      desc: '系统自动完成解码与色彩空间转换，将图像等比缩放并中心裁剪至 288 × 288，再按 ImageNet 统计量做归一化，保证输入分布与训练阶段一致。',
      stage: 'Step 02 · Preprocess',
    },
    {
      title: '模型推理',
      desc: 'ResNet50 与 ResNet101 双模型并行提取特征，集成后输出良恶性概率。开启 ONNX INT8 加速，单张推理耗时约 22–65ms，并同步给出 7 类病变类型参考。',
      stage: 'Step 03 · Inference',
    },
    {
      title: '结果解读',
      desc: '查看恶性/良性概率与置信度，对照 7 类病变类型参考，并按判定结果获取针对性的后续行动与就医建议。结果自动归档，可随时回看与导出。',
      stage: 'Step 04 · Result',
    },
  ]

  // 系统功能（文案与配色均贴合项目实际数据，勿随意改动数字）
  // en      = 卡片内英文小标题（主标题下方）
  // descEn  = 中文描述的英文对照，显示在中文正文下方
  const features = [
    {
      icon: '📤',
      title: '便捷上传',
      en: 'UPLOAD',
      desc: '支持拖拽或点击上传 JPG / PNG / BMP / WEBP 格式图像，单张不超过 10MB。上传后即时预览原图，可填写病变部位与发现时间等备注，便于后续对照复查。',
      descEn: 'Drag-and-drop or click to upload JPG / PNG / BMP / WEBP images, up to 10 MB each. The original image is previewed instantly, and you can add notes such as lesion location and date of discovery for later comparison.',
      tone: 'blue',
    },
    {
      icon: '🧠',
      title: 'AI 智能识别',
      en: 'INFERENCE',
      desc: '基于 ResNet50 / ResNet101 双模型集成推理，迁移学习配合数据增强训练，输出恶性概率与良性概率。测试集准确率 85.45%，AUC 0.9287，单张推理约 22–65ms。',
      descEn: 'Dual-model ensemble inference (ResNet50 / ResNet101) with transfer learning and data augmentation, outputting malignant and benign probabilities. Test accuracy 85.45%, AUC 0.9287, single-image inference in about 22–65 ms.',
      tone: 'purple',
    },
    {
      icon: '📊',
      title: '可视化结果',
      en: 'VISUALIZE',
      desc: '以置信度进度条与恶性/良性概率对比直观呈现判断依据，并额外给出 7 类病变类型参考（如黑色素瘤、基底细胞癌等）。提供筛查 / 平衡 / 精确三种阈值模式，可按「宁可误报不可漏诊」原则调整。',
      descEn: 'Confidence bars and malignant/benign probability comparison make the basis of each decision clear, plus a 7-class lesion type reference (melanoma, basal cell carcinoma, etc.). Three threshold modes — Screening, Balanced and Accurate — let you trade false positives against missed diagnoses.',
      tone: 'teal',
    },
    {
      icon: '💊',
      title: '健康建议',
      en: 'ADVICE',
      desc: '根据判定结果给出针对性后续行动：倾向良性时提示定期自查与日常防晒要点；倾向恶性时建议尽快到皮肤科就诊，并附就诊前注意事项与就医指导。',
      descEn: 'Targeted next steps based on the result: for benign findings, regular self-checks and daily sun protection tips; for malignant findings, a prompt visit to a dermatologist, with pre-visit precautions and guidance.',
      tone: 'green',
    },
    {
      icon: '🗂',
      title: '历史记录',
      en: 'HISTORY',
      desc: '登录后自动归档每次检测，支持按结果筛选、翻页查看、查看原图与详情，并可导出 CSV，用于长期跟踪同一部位病变的变化趋势。',
      descEn: 'Every detection is archived automatically after signing in. Filter by result, page through records, view the original image and details, and export to CSV to track how a lesion on the same site changes over time.',
      tone: 'amber',
    },
    {
      icon: '🔒',
      title: '数据安全',
      en: 'SECURITY',
      desc: '密码采用 PBKDF2-SHA256 加盐哈希（12 万次迭代）存储，登录使用 JWT 令牌认证；检测数据保存在服务端本机，医疗图像的隐私保护优先于便利性。',
      descEn: 'Passwords are stored as salted PBKDF2-SHA256 hashes (120,000 iterations) and authentication uses JWT tokens. Detection data stays on the local server — for medical images, privacy comes before convenience.',
      tone: 'rose',
    },
  ]

  // 调参预览页可用 ?wide=1280 覆盖「系统功能」区容器宽度；不带参数时为 undefined（走 CSS）
  const wrapStyle = (() => {
    if (typeof window === 'undefined') return undefined
    const w = new URLSearchParams(window.location.search).get('wide')
    return w ? { maxWidth: `${parseInt(w, 10)}px` } : undefined
  })()

  return (
    <div>
      {/* Hero —— Trajectory 风格：全屏 + 两行错位巨字 + 居中纸飞机 + 滚动合并/淡出
          ⚠️ 背景为浅色渐变，文字统一用深海军蓝 #334861 系保证对比度 */}
      <section
        ref={heroRef}
        className="hero-section relative overflow-hidden"
        style={{ color: '#334861', '--hero-prog': heroProg }}
      >
        {/* 渐变底图 */}
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/app/images/hero-bg.jpg')" }}
          aria-hidden="true"
        />
        {/* 点阵云（screen 混合叠在渐变上，形成原站那种云层质感）
            三朵云各挂一个缓慢左右浮动的动画，幅度小、周期长、相位错开 */}
        <img
          src="/app/images/cloud-1.png"
          alt=""
          aria-hidden="true"
          className="cloud-drift pointer-events-none absolute -left-[14%] top-[2%] w-[46%] max-w-none opacity-80 mix-blend-screen"
        />
        <img
          src="/app/images/cloud-2.png"
          alt=""
          aria-hidden="true"
          className="cloud-drift-slow pointer-events-none absolute right-[-10%] top-[36%] w-[38%] max-w-none opacity-70 mix-blend-screen"
        />
        <img
          src="/app/images/cloud-wide.png"
          alt=""
          aria-hidden="true"
          className="cloud-drift-wide pointer-events-none absolute left-[6%] bottom-[-12%] w-[60%] max-w-none opacity-45 mix-blend-screen"
        />
        {/* 纸飞机 + 金色粒子拖尾（居中，随滚动飞离） */}
        <HeroPlane />

        {/* 内容层 */}
        <div className="relative z-10 mx-auto flex h-full max-w-7xl flex-col px-6 md:px-10">
          {/* 顶部要点胶囊（随滚动淡出） */}
          <div className="hero-fade-slow pt-10">
            <div
              className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs"
              style={{ background: 'rgba(255,255,255,0.55)', backdropFilter: 'blur(6px)' }}
            >
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              深度学习模型 · ResNet50 · 医疗影像分析
            </div>
          </div>

          {/* 两行错位巨字：初始 左上/右下 拉开，随滚动向中线靠拢并合并成一行 */}
          <div className="relative flex flex-1 items-center">
            <h1 className="hero-title w-full select-none">
              <span className="hero-line hero-line-a">洞察入微</span>
              <span className="hero-line hero-line-b">防患未然</span>
            </h1>
          </div>

          {/* 右下角：说明文字 + 按钮（随滚动淡出） */}
          {/* max-w-lg(512px)：原 max-w-md(448px) 会让最后的「具。」孤字掉到第 4 行 */}
          <div className="hero-fade-fast flex flex-col items-start gap-4 pb-12 md:ml-auto md:max-w-lg md:items-end md:text-right">
            <p className="text-sm leading-relaxed opacity-80">
              上传皮肤病变部位的图像，系统基于深度残差网络自动分析病变特征，
              <br className="hidden md:block" />
              判断其良恶性倾向并提供健康建议，为皮肤健康自检提供便捷的辅助工具。
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/detect"
                className="px-6 py-3 rounded-lg font-semibold transition shadow-lg"
                style={{ background: '#334861', color: '#f7f9e8' }}
              >
                开始检测 →
              </Link>
              {!user && (
                <Link
                  to="/register"
                  className="px-6 py-3 rounded-lg font-medium transition"
                  style={{ border: '1px solid rgba(51,72,97,0.45)', color: '#334861' }}
                >
                  注册账号
                </Link>
              )}
            </div>
          </div>

          {/* 状态卡（hero 底部，随滚动淡出）
              四格 = 2 个系统指标（模型状态/识别精度）+ 2 个用户入口（医疗问答/我的检测）
              ⚠️ 识别精度数字来源：models_vE_r101_288 集成模型测试集评估
                 accuracy 85.45% / AUC 0.9287（与「系统功能」轮播 INFERENCE 卡一致，改数须两处同步）
              可点击的格子带 to=：模型状态→/detect、医疗问答→/chat、我的检测→/history
              （后两者受 RequireAuth 保护，未登录点进去会自动跳登录页，符合既有逻辑） */}
          <div className="hero-fade-fast grid grid-cols-2 md:grid-cols-4 gap-4 pb-10">
            <StatCard
              label="模型状态"
              value={health?.model?.ready ? '已就绪' : '未就绪'}
              sub={health?.model?.arch?.toUpperCase() || '—'}
              ok={health?.model?.ready}
              to="/detect"
            />
            <StatCard
              label="医疗问答"
              value={chatSt?.text_model_ready ? '在线' : '离线'}
              sub={
                chatSt?.text_model_ready
                  ? `${(chatSt.text_model || '').split(':')[0]} 医疗模型`
                  : '问答模型未就绪'
              }
              ok={!!chatSt?.text_model_ready}
              to="/chat"
            />
            <StatCard
              label="识别精度"
              value="85.45%"
              sub="AUC 0.9287（测试集）"
              ok
            />
            <StatCard
              label="我的检测"
              value={user ? `${stats?.total ?? 0} 次` : '未登录'}
              sub={user && stats ? `恶性 ${stats.malignant} / 良性 ${stats.benign}` : '登录后统计'}
              ok={!!user}
              to="/history"
            />
          </div>
        </div>
      </section>

      {/* 功能（轮播：点击圆点 / 左右拖动切换，慢速自动播放）
          整段用米黄绿底衬托彩色卡片，与医疗蓝主题呼应
          容器宽度与「检测流程」统一为 .process-wrap，保证两区标题左对齐
          ?wide=数值 可覆盖宽度（调参预览页用，不带参数时行为不变） */}
      <section className="feature-section">
        <div className="process-wrap mx-auto px-4 py-14" style={wrapStyle}>
          <h2 className="section-heading">系统功能</h2>
          <p className="section-subheading">
            覆盖从图像上传到结果解读的完整检测流程
          </p>
          <FeatureCarousel
            items={features}
            interval={5000}
            slideRatio={0.6}
            cardMinH={420}
            showEn
          />
        </div>
      </section>

      {/* 流程说明（米色底，与「系统功能」同款）
          标题与步骤同在左栏，演示框顶部与标题齐平、底部与最后一步齐平 */}
      <section className="process-section">
        <div className="process-wrap mx-auto px-4 py-14">
          <ProcessShowcase
            steps={processSteps}
            interval={8000}
            heading="检测流程"
            subheading="四步完成一次检测，点击左侧步骤查看各环节演示"
          />
        </div>
      </section>

      {/* 免责 */}
      <section className="max-w-4xl mx-auto px-4 py-12">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
          <h3 className="font-semibold text-amber-800 mb-2 flex items-center gap-2">
            ⚠️ 医疗免责声明
          </h3>
          <p className="text-sm text-amber-800/90 leading-relaxed">
            本系统仅作为皮肤健康自检的辅助工具，其检测结果由深度学习模型生成，
            <b>仅供参考，不构成医疗诊断，不能替代专业医生的诊断与治疗</b>。
            皮肤病变的确诊需要专业医生结合皮肤镜检查、组织病理学活检等手段综合判断。
            如有任何疑虑或不适，请及时就医咨询专业皮肤科医生。
          </p>
        </div>
      </section>
    </div>
  )
}

function StatCard({ label, value, sub, ok, to }) {
  const body = (
    <>
      <div className="text-[11px] mb-1" style={{ color: 'rgba(51,72,97,0.62)' }}>{label}</div>
      <div className="text-lg font-bold flex items-center gap-2">
        {value}
        {ok != null && (
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              ok ? 'bg-green-500' : 'bg-amber-500'
            }`}
          />
        )}
      </div>
      <div className="text-[11px] mt-0.5 truncate" style={{ color: 'rgba(51,72,97,0.5)' }}>{sub}</div>
    </>
  )

  const baseStyle = {
    background: 'rgba(255,255,255,0.62)',
    backdropFilter: 'blur(8px)',
    border: '1px solid rgba(51,72,97,0.14)',
  }

  // to 存在 → 整格可点击跳转（hover 时微弱抬升 + 边框加深，不做花哨动效）
  if (to) {
    return (
      <Link
        to={to}
        className="stat-card-clickable rounded-xl px-4 py-3 block transition"
        style={baseStyle}
      >
        {body}
      </Link>
    )
  }

  return (
    <div className="rounded-xl px-4 py-3" style={baseStyle}>
      {body}
    </div>
  )
}
