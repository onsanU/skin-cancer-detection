# 皮肤癌图像检测系统

> 基于深度学习的皮肤病变图像辅助筛查系统 —— 上传皮肤镜图像，自动判断**良性/恶性**，并给出**可能的病变类型**作为参考。

**课程**：项目实践（AI 应用开发 · 图像分类 · 医疗影像）｜**作者**：嘉应学院 数据科学 2027 届

---

## ⚠️ 医疗免责声明

本系统仅作为皮肤健康自检的**辅助工具**，检测结果由 AI 模型生成，**仅供参考，不构成医疗诊断，不能替代专业医生的诊断与治疗**。如有任何疑虑或不适，请及时就医咨询专业医生。

---

## 快速开始（三步）

### 方式一：Windows 双击（最简单，推荐）

```
双击  启动服务.bat      →  自动启动并打开浏览器
双击  停止服务.bat      →  关闭服务
```

### 方式二：WSL / Linux 命令行

```bash
cd "/mnt/d/Project/JXprojiect/Hermes-project/project/皮肤癌图像系统"
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
| **前台检测** | http://127.0.0.1:8000/app/ | 上传图片、查看结果、历史记录 |
| **管理后台** | http://127.0.0.1:8000/admin/ | 运营管理（账号 `admin` / `<密码>`） |
| **API 文档** | http://127.0.0.1:8000/docs | Swagger 交互式接口文档 |

> 首次启动需加载 2 个集成模型 + 7 类模型，约 **10-20 秒**；启动脚本会自动等待就绪并检查健康状态。

---

## 项目亮点

| 指标 | 实测值 | 说明 |
|------|--------|------|
| **准确率** | **85.45%** | 集成模式（2 模型），测试集 213 张 |
| **AUC** | **0.9287** | 比 accuracy 更抗阈值/样本量影响 |
| **筛查模式漏诊率** | **3.39%** | 阈值 0.28，恶性召回 96.61%，"宁可误报不可漏诊" |
| **模型压缩** | **3.93x** | ONNX INT8 量化，90MB → 22.9MB，精度损失仅 0.47% |
| **推理延迟** | **22-62ms** | 单张图像，集成模式 GPU 推理 |
| **7 类类型参考** | 74.32% | 在良恶性之外额外给出病变类型提示 |

**关键技术点**：

- **病灶级数据划分**（按 `lesion_id` 分组）—— 防止同一病灶的多张图跨训练/测试集导致数据泄漏、准确率虚高
- **差分学习率 + warmup** —— backbone 用 head 的 1/10 学习率保护预训练特征，前 5 轮预热避免"一冲顶就跌"
- **阈值调优** —— 提供筛查/平衡/精确三种工作模式，医疗场景可用 0.94% 准确率换取漏诊率降低 62%
- **双模型并存** —— 二分类模型管"良性/恶性"（主结论），7 类模型管"可能是哪种"（参考信息），主指标零风险
- **ONNX INT8 量化** —— 加载仅 0.22s（比 PyTorch 快 21 倍），无需 GPU 即可部署

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| 深度学习 | PyTorch 2.11 + cu128（RTX 5070 / 8G 显存） |
| 模型 | ResNet50 / ResNet101（迁移学习） |
| 图像处理 | OpenCV / Pillow |
| 后端 | FastAPI + Uvicorn |
| 前端 | React 18 + Vite 5 + TailwindCSS 3 |
| 数据库 | SQLite3（原生 `sqlite3`，零额外依赖） |
| 认证 | 自实现 JWT（HS256）+ PBKDF2 密码哈希 |
| 部署 | ONNX Runtime（INT8 量化推理） |

---

## 目录结构

```
皮肤癌图像系统/
├── start.sh / stop.sh          一键启动 / 停止（WSL）
├── 启动服务.bat / 停止服务.bat  一键启动 / 停止（Windows 双击）
│
├── backend/                    后端服务
│   ├── app/
│   │   ├── main.py             应用入口（挂载 /app 前端 + /admin 管理后台）
│   │   ├── config.py           ★ 配置中心（模型候选、阈值预设、免责声明）
│   │   ├── database.py         SQLite 初始化 + 查询函数
│   │   ├── admin_api.py        管理后台 11 接口
│   │   ├── routers/            auth / predict / records 路由
│   │   └── services/
│   │       ├── predictor.py    ★ 推理核心（集成 + 双模型 + 自动探测）
│   │       └── onnx_backend.py ONNX INT8 推理后端
│   ├── static/admin/           管理后台前端（AdminLTE，6 页面）
│   ├── frontend/dist/          前端构建产物（自动挂载到 /app/）
│   └── skin_cancer.db          SQLite 数据库
│
├── frontend/                   React 前端源码
│   └── src/pages/              首页 / 检测 / 历史 / 登录注册
│
├── src/                        ★ 训练与算法脚本
│   ├── train_resnet50.py       训练（支持任意 N 类，差分 lr/warmup/AMP/早停）
│   ├── threshold_tuning.py     阈值扫描（秒级出结果，不用重训）
│   ├── ensemble_eval.py        模型集成 + TTA 评估
│   └── onnx_quantize.py        ONNX INT8 量化
│
├── data_scripts/               数据预处理（病灶级划分防泄漏）
│   └── prepare_dataset{,_v2,_v3_balanced,_7class}.py
│
├── dataset/                    数据集（硬链接，几乎不额外占盘）
│   ├── processed_v2_full/      二分类：训练 9802 / 测试 213
│   └── processed_7class/       七分类：训练 9832 / 测试 183
│
├── models_v2_full/             部署模型（ResNet50@224，acc 84.98%）
├── models_vE_r101_288/         ResNet101@288（AUC 0.9187 最高）
├── models_compressed/          二分类 ONNX INT8（22.9MB）
├── models_7class_r50/          七分类 PyTorch
├── models_compressed_7class/   七分类 ONNX INT8（22.9MB）
│
├── scripts/system_test.py      系统自动化测试（32 用例）
├── 交付文件/                   ★ 交付物（文档/PPT/讲稿/RAG语料）
└── docs/                       开发过程文档与实验记录
```

---

## API 概览

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
| — | `/admin/api/*` | 管理后台 11 个接口（详见交付文件 05-API接口文档） |

**示例**：

```bash
# 1. 登录拿 token（用户名/密码见部署时的 .env 配置）
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<用户名>","password":"<密码>"}' -o /tmp/login.json

# 2. 上传图片检测（登录态会保存历史记录）
curl -s -X POST http://127.0.0.1:8000/api/predict \
  -H "Authorization: Bearer $(python3 -c "import json;print(json.load(open('/tmp/login.json'))['token'])")" \
  -F "threshold=0.51" \
  -F "file=@/path/to/lesion.jpg"
```

---

## 常见问题 / 故障排查

**Q: 启动后浏览器打不开 / 显示连接失败？**
1. 等 10-20 秒（集成模型加载需要时间）
2. 看日志：`tail -f logs/backend.log`
3. 确认端口没被占：`ss -ltnp | grep 8000`

**Q: 提示 "端口 8000 已被占用"？**
启动脚本会自动检测：若占用者是本项目旧服务，会自动停止并重启；若是其它程序，请换端口 `bash start.sh --port 8080`

**Q: 推理很慢 / GPU 利用率低？**
- 检查是否有其它程序抢显存（Ollama 加载大模型会占用）：`nvidia-smi`
- 释放：`ollama stop <模型名>` 或设置 `keep_alive:0`

**Q: `/app/` 页面 404？**
前端未构建。执行：`cd frontend && npm install && npm run build`

**Q: 训练/推理时数据放在 D 盘很慢？**
WSL 读 Windows 挂载盘（`/mnt/d`）的小文件极慢（实测慢 8 倍），会导致 GPU 饿死。训练前把数据集复制到 WSL 本地盘：`cp -r dataset/processed_v2_full ~/skin_cancer_data/`

**Q: 显存不够？**
ResNet50@224 batch=32 仅占 1.6-2.3GB，8G 显存完全够用。若同时跑其它 GPU 任务，先停掉。

**Q: 想重新训练模型？**
```bash
cd src
~/shixun-venv/bin/python train_resnet50.py \
  --data ../dataset/processed_v2_full \
  --arch resnet50 --img-size 224 \
  --epochs 30 --warmup 5 --lr 5e-4
```

**Q: 改了 `config.py` 没生效？**
`config.py` 在启动时读取，改完**必须重启服务**：`bash stop.sh && bash start.sh --bg`

---

## 实验记录（模型迭代过程）

| 实验 | 训练数据 | 增强 | lr(head/backbone) | acc | 恶性Recall | AUC |
|------|---------|------|------------------|-----|-----------|-----|
| 基线 | 792 张 | medium | 1e-3 / 1e-4 | 81.69% | 88.98% | 0.855 |
| 方案A | 792 张 | strong | 3e-4 / 1e-5 | 81.69% | 85.59% | 0.861 |
| **v2 全量** | **9802 张** | medium | 5e-4 / 5e-5 | 84.98% | 88.98% | 0.9162 |
| 方案D | 9802 张 | medium | + warmup 5 | 83.57% | 87.29% | 0.9146 |
| 实验C | 3672 张（平衡） | medium | 1e-4 / 2e-6 | 80.75%（中止） | 88.14% | 0.890 |
| **方案E** | 9802 张 | medium | R101@288 + warmup 3 | 84.98% | 86.44% | **0.9187** |
| **集成** | — | — | 2 模型概率平均 | **85.45%** | 87.29% | **0.9287** |

**核心结论**：
1. **数据量 > 调参** —— 792 → 9802 张，acc +3.3%、AUC +6.1%
2. **学习率两头都失败** —— 太大：epoch 1 即最佳后一路下滑；太小：过拟合消失但学不动
3. **warmup 是正解** —— 训练曲线从"一冲顶就跌"变成"稳步上升"
4. **AUC 已到数据天花板**（0.89-0.92）—— 剩下的是阈值取舍而非模型问题
5. **模型容量不是瓶颈** —— ResNet101@288 让 AUC 涨 0.25% 但 acc 一动不动

---

## 数据集

**HAM10000**（Human Against Machine with 10000 training images）
- 来源：Kaggle `kmader/skin-cancer-mnist-ham10000` ｜ 原版 Harvard Dataverse
- 规模：10015 张皮肤镜图像 / 7470 个病灶
- 许可：CC BY-NC-SA 4.0（**非商用**）
- 7 类原始标注 → 映射为二分类：

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

---

## 交付物

`交付文件/` 目录下包含全部课程交付物：

| # | 文件 |
|---|------|
| 01 | 需求分析与系统设计文档 |
| 02 | PRD 产品需求文档 |
| 03 | UI/UX 设计文档 |
| 04 | 数据库设计文档 |
| 05 | API 接口文档（24 接口） |
| 06 | 测试报告（240 项断言） |
| 07 | 部署运维手册 |
| 08 | AI 协作开发教程 |
| 09 | 项目说明文档（参数文档） |
| 10 | 项目汇报.pptx（16 页） |
| 11 | 汇报讲稿.md |
| 12 | 演示前开机清单.md |
| — | RAG 语料库（18 份 + 提示词）/ 演示存档 / ppt-source |

---

## 开发环境

- **系统**：Windows 11 + WSL2 (Ubuntu)
- **GPU**：NVIDIA RTX 5070 Laptop 8G（Blackwell 架构 → 必须 torch≥2.7 + cu128）
- **Python**：`~/shixun-venv`（torch 2.11.0+cu128 / fastapi 0.141.1 / uvicorn 0.52.4）
- **Node**：前端构建用（Vite 5）

依赖安装：
```bash
~/shixun-venv/bin/pip install fastapi uvicorn pillow python-multipart email-validator
~/shixun-venv/bin/pip install scikit-learn matplotlib opencv-python-headless torchmetrics   # 训练用
~/shixun-venv/bin/pip install onnx onnxruntime                                            # 量化用
```

---

## 许可

本项目为课程作业，仅供学习交流使用。数据集 HAM10000 遵循 CC BY-NC-SA 4.0 许可（**禁止商用**）。
