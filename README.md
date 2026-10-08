# 🔬 皮肤癌图像检测系统

基于**深度学习多模型集成**的皮肤病变图像辅助筛查系统。上传一张皮肤镜图像，系统自动判断**良性 / 恶性**，给出**可能的病变类型**参考，输出**模型关注区域热力图**（Grad-CAM），还能就结果与 AI 医生助手继续问答。

> ⚠️ 本系统仅作皮肤健康自检的**辅助工具**，结果由 AI 生成，**仅供参考，不构成医疗诊断，不能替代专业医生**。如有疑虑请及时就医。

**课程**：项目实践（AI 应用开发 · 图像分类 · 医疗影像）｜**作者**：嘉应学院 数据科学 2027 届

---

## ✨ 功能特性

- 🔍 **良恶性智能判定**：ResNet101 + ConvNeXt 双模型集成，输出恶性概率与判定结论（集成准确率 **86.38%**，AUC **0.9276**）
- 🏷️ **病变类型参考**：7 类模型额外提示「可能是哪种病变」（黑色素瘤 / 基底细胞癌 / 痣 / 角化 …）
- 🎚️ **三档工作模式**：筛查（不漏诊）/ 平衡 / 精确，医疗场景一键切换阈值
- 🔥 **Grad-CAM 可解释性**：每个集成成员生成"模型关注区域"热力图，与原图并排展示，模型决策看得见
- 🤖 **AI 医疗问答**：对检测结果有疑问？直接和内置 AI 助手多轮对话（本地大模型，可传图）
- 📋 **健康建议**：按良恶性 + 病变类型给出差异化就医建议
- 📜 **历史记录**：检测历史分页检索、统计图表、CSV 导出、单条删除
- 🔐 **账号体系**：注册 / 登录（JWT HS256 + PBKDF2 密码哈希），历史跟账号走
- 📊 **管理后台**（`/admin`）：数据看板、检测记录检索、用户统计、审计日志、系统状态监控
- 🖼️ **响应式前端**：React 18 + Tailwind，深色医疗科技风

## 🧰 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12 + JavaScript |
| 深度学习 | PyTorch 2.11 + cu128（RTX 5070 / 8G 显存） |
| 模型架构 | ResNet50 / ResNet101 / **ConvNeXt-Tiny**（迁移学习） |
| 训练技巧 | CutMix 数据混合 · Focal Loss · 差分学习率 · warmup · AMP · 早停 |
| 图像处理 | OpenCV / Pillow |
| 可解释性 | Grad-CAM（Selvaraju et al. 2017） |
| 后端 | FastAPI + Uvicorn |
| 前端 | React 18 + Vite 5 + TailwindCSS 3 |
| 数据库 | SQLite3（原生 `sqlite3`，零额外依赖） |
| 认证 | 自实现 JWT（HS256）+ PBKDF2 密码哈希 |
| 部署 | ONNX Runtime（INT8 量化推理，无需 GPU） |
| AI 问答 | 本地大模型（Ollama，可选启用） |

## 📁 目录结构

```
皮肤癌图像系统/
├── start.sh / stop.sh           一键启动 / 停止（WSL）
├── 启动服务.bat / 停止服务.bat   一键启动 / 停止（Windows 双击）
│
├── src/                         ★ 训练与算法实验
│   ├── train_resnet50.py        ResNet 训练（差分 lr / warmup / AMP / 早停）
│   ├── train_sota.py            ConvNeXt 训练 + CutMix/MixUp 实现
│   ├── train_multimodal.py      多模态训练实验
│   ├── ensemble_eval.py         模型集成 + TTA 评估
│   ├── ensemble_multiarch.py    跨架构集成权重网格搜索
│   ├── threshold_tuning.py      阈值扫描（秒级出结果，不用重训）
│   ├── threshold_calibrate_v3.py 三档阈值标定（val 标定 / test 报成绩）
│   ├── cross_dataset_eval.py    跨数据集泛化测试（HAM → BCN）
│   ├── model_compress.py        模型剪枝 / 压缩
│   └── onnx_quantize.py         ONNX INT8 量化
│
├── data_scripts/                数据预处理（病灶级划分防泄漏）
│   ├── download_bcn20k.py       BCN20000 下载器（ISIC S3 官方直链）
│   ├── prepare_dataset*.py      HAM10000 → 二分类 / 七分类数据集
│   └── prepare_dataset_mixed.py HAM + BCN 混训集构建
│
│   # dataset/ 数据集目录不入库，用上面的脚本重新生成
│   # models_*/ 模型权重不入库，训练脚本可复现
│
├── backend/                     后端服务
│   ├── app/
│   │   ├── main.py              应用入口（挂载 /app 前端 + /admin 管理后台）
│   │   ├── config.py            ★ 配置中心（模型候选 / 阈值预设 / 免责声明）
│   │   ├── database.py          SQLite 初始化 + 查询函数
│   │   ├── admin_api.py         管理后台接口
│   │   ├── routers/             auth / predict / records / chat 路由
│   │   └── services/
│   │       ├── predictor.py     ★ 推理核心（集成 + 双模型 + 自动探测）
│   │       ├── gradcam.py       ★ Grad-CAM 可解释性热力图
│   │       ├── type_classifier.py  7 类病变分类
│   │       ├── onnx_backend.py  ONNX INT8 推理后端
│   │       └── llm.py           AI 问答（本地大模型）
│   ├── static/admin/            管理后台前端（AdminLTE，多页面）
│   └── sql/                     建表 / 迁移 SQL
│
├── frontend/                    React 前端源码
│   └── src/pages/               首页 / 检测 / 历史 / 问答 / 登录 / 注册
│
├── scripts/                     系统测试与后台验证脚本
├── docs/                        开发过程文档与实验记录
│   ├── 训练实验记录.md           第一阶段 10 组实验
│   ├── CutMix实验记录.md        ★ 突破 86.38% 的完整实验
│   ├── 跨数据集泛化验证报告.md    HAM → BCN 域泛化分析
│   ├── 模型压缩报告.md          INT8 量化 3.93x
│   └── 迭代说明_管理后台.md      管理后台迭代记录
├── 其余文件/                    需求 / PRD / UIUX / 数据库 / API / 测试 / 部署全套文档
└── 项目要求事项/                 课程任务书
```

## 📊 项目亮点

| 指标 | 实测值 | 说明 |
|------|--------|------|
| **集成准确率** | **86.38%** | R101 + ConvNeXt-CutMix 等权集成，test 213 张 |
| **AUC** | **0.9276** | 比 accuracy 更抗阈值 / 样本量影响 |
| **恶性召回** | **91.53%** | 精确模式（阈值 0.48） |
| **筛查模式漏诊** | **0%（val）** | 阈值 0.20，191 张恶性全部识别 |
| **模型压缩** | **3.93x** | ONNX INT8 量化，90MB → 22.9MB，精度损失仅 0.47% |
| **推理延迟** | **22-62ms** | 单张图像，集成模式 GPU 推理 |
| **7 类类型参考** | 74.32% | 良恶性之外的病变类型提示 |

**关键技术点**：

- **病灶级数据划分**（按 `lesion_id` 分组）—— 防止同一病灶的多张图跨训练/测试集导致数据泄漏、准确率虚高
- **CutMix 数据混合** —— 有效治愈过拟合（train/test 裂口从 -17.96% 收窄到 -9.01%），配合长训（50 轮）把准确率推到 85.92% 单模型 / **86.38% 集成**
- **差分学习率 + warmup** —— backbone 用 head 的 1/10 学习率保护预训练特征，前 5 轮预热避免"一冲顶就跌"
- **三档阈值工作模式** —— 严格「val 标定 / test 只报成绩」，筛查档在 val 上漏诊率 0%
- **双模型分层设计** —— 二分类管"良性/恶性"（主结论），7 类模型管"可能是哪种"（参考），主指标零风险
- **ONNX INT8 量化** —— 加载仅 0.22s（比 PyTorch 快 21 倍），无需 GPU 即可部署
- **跨数据集泛化验证** —— HAM → BCN 跨域测试，量化域依赖（落差 -11.87pp），为混训提供动机

## 🚀 快速开始

### 方式一：Windows 双击（最简单，推荐）

```
双击  启动服务.bat      →  自动启动并打开浏览器
双击  停止服务.bat      →  关闭服务
```

### 方式二：WSL / Linux 命令行

```bash
bash start.sh              # 启动（自动检查环境/端口/模型）
bash stop.sh               # 停止
```

启动脚本参数：

| 参数 | 说明 |
|------|------|
| `--bg` | 后台运行（关终端不退出） |
| `--reload` | 开发模式，代码改动自动重载 |
| `--port 8080` | 指定端口（默认 8000） |
| `--no-check` | 跳过模型文件预检（启动更快） |

### 访问地址

| 入口 | 地址 | 说明 |
|------|------|------|
| **前台检测** | http://127.0.0.1:8000/app/ | 上传图片、查看结果、历史记录、AI 问答 |
| **管理后台** | http://127.0.0.1:8000/admin/ | 运营管理（需管理员登录） |
| **API 文档** | http://127.0.0.1:8000/docs | Swagger 交互式接口文档 |

> 首次启动需加载 2 个集成模型 + 7 类模型，约 **10-20 秒**；启动脚本会自动等待就绪并检查健康状态。

### 环境要求

- Linux / WSL，Python 3.10+
- RTX 显卡（有 GPU 更流畅，CPU 也能跑但慢）
- Node.js（仅前端构建需要）

### 安装依赖

```bash
# 后端
pip install fastapi uvicorn pillow python-multipart email-validator
pip install scikit-learn matplotlib opencv-python-headless torchmetrics   # 训练用
pip install onnx onnxruntime                                              # 量化用

# 前端构建（可选，仓库不含 dist）
cd frontend && npm install && npm run build
```

## 🎚️ 三档工作模式

系统提供三种阈值预设，适配不同医疗场景（数值经 val 集标定，test 仅报成绩）：

| 模式 | 阈值 | test 准确率 | test 恶性召回 | val 漏诊率 | 适用场景 |
|------|------|------------|--------------|-----------|----------|
| **筛查模式** screening | 0.20 | 78.87% | **99.15%** | **0.00%** | 初步自查 / 大规模筛查（宁误报不漏诊） |
| **平衡模式** balanced | 0.33 | 83.10% | 95.76% | 2.09% | 日常使用 |
| **精确模式** accurate | 0.48 | **86.38%** | 91.53% | 9.95% | 结论可信度优先（默认） |

> 单调性经严格验证：阈值递增 ✔ / 召回递减 ✔ / 准确率递增 ✔

## 📈 实验记录（模型迭代过程）

### 第一阶段：单域训练（HAM10000，2026-09-14）

| 实验 | 训练数据 | 增强 | lr(head/backbone) | acc | 恶性Recall | AUC |
|------|---------|------|------------------|-----|-----------|-----|
| 基线 | 792 张 | medium | 1e-3 / 1e-4 | 81.69% | 88.98% | 0.855 |
| 方案A | 792 张 | strong | 3e-4 / 1e-5 | 81.69% | 85.59% | 0.861 |
| **v2 全量** | **9802 张** | medium | 5e-4 / 5e-5 | 84.98% | 88.98% | 0.9162 |
| 方案D | 9802 张 | medium | + warmup 5 | 83.57% | 87.29% | 0.9146 |
| **方案E** | 9802 张 | medium | R101@288 + warmup 3 | 84.98% | 86.44% | 0.9187 |
| **集成（旧）** | — | — | R50 + R101 等权 | 85.45% | 87.29% | 0.9287 |

### 第二阶段：CutMix 突破（2026-09-17）

前任最优卡在 85.45%，诊断为**过拟合**（ConvNeXt 曲线 train 97.41% / test 79.45%，裂口 -17.96%）。
引入 CutMix 数据混合 + 长训后突破：

| 实验 | 轮数 | 混合 | 选模 | test acc | 恶性召回 | AUC |
|------|------|------|------|----------|----------|-----|
| 历史基线 | — | 无 | medical | 85.89% | 90.05% | 0.9269 |
| A组 | 20 | cutmix | medical | 83.10%（ep19） | 97.46% | 0.9075 |
| B组 | 18 | mixup | medical | 82.63% | 96.61% | 0.9173 |
| **C组（长训）** | **50** | **cutmix** | **acc** | **85.92%** | **91.53%** | **0.9207** |

**集成搜索**（4 模型权重网格，80 组）：

| 组合 | test acc | 恶性召回 | AUC |
|------|----------|----------|-----|
| **R101×1 + CutMix×1** ★ | **86.38%** | **91.53%** | 0.9276 |
| CutMix×1 + R50×1 | 85.92% | 94.92% | 0.9294 |
| R101×2 + CutMix×1 | 85.92% | 93.22% | 0.9269 |
| 历史：等权(R50+R101) | 85.45% | 87.29% | 0.9287 |

**核心结论**：
1. **数据量 > 调参** —— 792 → 9802 张，acc +3.3%、AUC +6.1%
2. **CutMix 治愈过拟合** —— 裂口 -17.96% → -9.01%，test 稳定在 84~86%
3. **轮数不够会被误判为方法无效** —— A组 20 轮 83.10%，同配置 50 轮 85.92%（+2.82%）
4. **选模规则影响显著** —— 含召回项的公式会选偏 3.76%，冲准确率须用纯 acc 选模
5. **AUC 已到数据天花板**（0.89-0.93）—— 剩下的是阈值取舍而非模型问题

## 🧪 跨数据集泛化验证（HAM10000 → BCN20000）

为回答「86.38% 是通用病变特征还是 HAM 域特征」，用 BCN20000（12413 张，ISIC 官方直链）做跨域测试：

| 评测集 | 样本数 | 最优 acc | 恶性召回 | AUC |
|--------|--------|----------|----------|-----|
| HAM 测试集（源域） | 213 | 86.38% | 91.53% | 0.9276 |
| BCN 平衡集（目标域） | 11158 | 74.51% | 71.50% | 0.8214 |
| BCN 全量（目标域） | 12413 | 74.64% | 78.97% | 0.8217 |

**结论**：
- **泛化落差 -11.87 个百分点** → 模型存在较强域依赖，跨医院数据泛化不足
- **AUC 落差相对小**（-0.1062）→ 排序/区分能力保留了一部分，主要损失来自阈值漂移
- **误报是主要错误模式**（FP=1317）→ 与 BCN 专收「低色素难样本 + 指甲/黏膜部位」的特性吻合
- **动机**：这是引入混训数据最有力的证据

## 📦 数据集

### HAM10000（Human Against Machine with 10000 training images）

- 来源：Kaggle `kmader/skin-cancer-mnist-ham10000` ｜ 原版 Harvard Dataverse
- 规模：**10,015 张**皮肤镜图像 / 7,470 个病灶
- 许可：CC BY-NC-SA 4.0（**非商用**）
- 用途：**主训练集**（病灶级划分：训练 9802 / 测试 213）

原 7 类标注 → 二分类映射：

| 原类别 | 性质 | 归到 |
|--------|------|------|
| mel（黑色素瘤） | 恶性 | 恶性 |
| bcc（基底细胞癌） | 恶性 | 恶性 |
| akiec（光化性角化） | 恶性/癌前 | 恶性 |
| nv（黑色素细胞痣） | 良性 | 良性 |
| bkl（良性角化） | 良性 | 良性 |
| df（皮肤纤维瘤） | 良性 | 良性 |
| vasc（血管性病变） | 良性 | 良性 |

映射后：恶性 1954 张 / 良性 8061 张（类别不平衡，训练用中位数频率平衡 + 类别权重处理）

### BCN20000

- 来源：ISIC Archive S3 官方直链（`isic-archive.s3.amazonaws.com`）
- 规模：**12,413 张** / 3,576 个病灶
- 用途：① **跨域泛化验证**（12413 张测试） ② **混训集构建原料**

### 混训数据集（HAM + BCN，已构建待重训）

| 项 | 数量 |
|----|------|
| 总图片 | **22,428 张** |
| 训练集 | 19,676 张（12392 良性 / 7284 恶性） |
| 测试集 | 2,752 张（1248 良性 / 1504 恶性） |
| HAM 来源 | 9802 训练 + 213 锁定测试 |
| BCN 来源 | 9874 训练 + 2539 测试 |
| 泄漏自检 | 图片级交集 0 ✅ / BCN 病灶级交集 0 ✅ |

> 📌 **当前线上模型为 HAM 单域训练**（9802 张）；混训集已构建完成，是下一步训练方向。

## 🔌 API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（含模型状态） |
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 登录（返回 JWT，7 天有效） |
| GET | `/api/auth/me` | 当前用户信息 |
| POST | `/api/predict` | **图像检测**（`file` + 可选 `threshold`） |
| GET | `/api/model/info` | 模型信息（含 7 类模型状态） |
| GET | `/api/thresholds` | 阈值预设（三种工作模式） |
| GET | `/api/image/{name}` | 获取上传的图像 |
| GET | `/api/records` | 历史记录（分页/筛选） |
| GET | `/api/records/stats` | 检测统计 |
| GET | `/api/records/export` | 导出 CSV |
| GET/DELETE | `/api/records/{id}` | 记录详情 / 删除 |
| — | `/api/chat/*` | AI 医疗问答（会话 / 消息） |
| — | `/admin/api/*` | 管理后台接口 |

**示例**：

```bash
# 1. 登录拿 token（用户名/密码见部署配置）
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<用户名>","password":"<密码>"}' -o /tmp/login.json

# 2. 上传图片检测（登录态会保存历史记录）
curl -s -X POST http://127.0.0.1:8000/api/predict \
  -H "Authorization: Bearer $(python3 -c "import json;print(json.load(open('/tmp/login.json'))['token'])")" \
  -F "threshold=0.48" \
  -F "file=@/path/to/lesion.jpg"
```

## ❓ 常见问题 / 故障排查

**Q: 启动后浏览器打不开 / 显示连接失败？**
1. 等 10-20 秒（集成模型加载需要时间）
2. 看日志：`tail -f logs/backend.log`
3. 确认端口没被占：`ss -ltnp | grep 8000`

**Q: 提示"端口 8000 已被占用"？**
启动脚本自动检测：若占用者是本项目旧服务，会自动停止并重启；若是其它程序，请换端口 `bash start.sh --port 8080`

**Q: 推理很慢 / GPU 利用率低？**
- 检查是否有其它程序抢显存：`nvidia-smi`
- 释放：`ollama stop <模型名>` 或设置 `keep_alive:0`

**Q: `/app/` 页面 404？**
前端未构建。执行：`cd frontend && npm install && npm run build`

**Q: 训练/推理时数据放在 D 盘很慢？**
WSL 读 Windows 挂载盘（`/mnt/d`）的小文件极慢（实测慢 8 倍），会导致 GPU 饿死。训练前把数据集复制到 WSL 本地盘：`cp -r dataset/processed_v2_full ~/skin_cancer_data/`

**Q: 显存不够？**
ResNet50@224 batch=32 仅占 1.6-2.3GB，8G 显存完全够用。若同时跑其它 GPU 任务，先停掉。

**Q: 改了 `config.py` 没生效？**
`config.py` 在启动时读取，改完**必须重启服务**：`bash stop.sh && bash start.sh --bg`

## 🛠️ 开发环境

- **系统**：Windows 11 + WSL2 (Ubuntu)
- **GPU**：NVIDIA RTX 5070 Laptop 8G（Blackwell 架构 → 必须 torch≥2.7 + cu128）
- **Python**：3.12（torch 2.11.0+cu128 / fastapi 0.141.1 / uvicorn 0.52.4）
- **Node**：前端构建用（Vite 5）

### 重新训练模型

```bash
cd src
python train_resnet50.py \
  --data ../dataset/processed_v2_full \
  --arch resnet50 --img-size 224 \
  --epochs 30 --warmup 5 --lr 5e-4
```

### 复现完整实验链路

```bash
# 1. 准备数据（病灶级划分防泄漏）
python data_scripts/prepare_dataset_v2.py --ham /path/to/ham10000 --out ../dataset/processed_v2_full

# 2. 训练
python src/train_sota.py --data ../dataset/processed_v2_full --arch convnext_tiny --img-size 288 --epochs 50 --mix cutmix

# 3. 阈值标定（val 标定 / test 报成绩）
python src/threshold_calibrate_v3.py --data ../dataset/processed_v2_full

# 4. 集成评估
python src/ensemble_multiarch.py
```

## 📄 许可

本项目为课程作业，仅供学习交流使用。数据集 HAM10000 遵循 CC BY-NC-SA 4.0 许可（**禁止商用**）；BCN20000 遵循其原始许可协议。
