# 皮肤癌图像检测系统 — 后端服务

基于 FastAPI 的模型推理服务，提供图像上传、良恶性判别、历史记录、用户管理接口。

## 技术栈

- **框架**: FastAPI + Uvicorn
- **模型**: PyTorch ResNet50（二分类：良性/恶性）
- **数据库**: SQLite3
- **图像处理**: Pillow + OpenCV

## 快速开始

```bash
# 1. 确认环境（使用训练同一个 venv）
~/shixun-venv/bin/python -c "import torch, fastapi; print('OK')"

# 2. 启动服务
cd backend
~/shixun-venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 访问
# API文档: http://127.0.0.1:8000/docs
# 健康检查: http://127.0.0.1:8000/api/health
```

## 目录结构

```
backend/
├── app/
│   ├── main.py              FastAPI 应用入口
│   ├── config.py            配置（模型路径、上传限制等）
│   ├── database.py          SQLite 连接与初始化
│   ├── models/              SQLAlchemy ORM 模型
│   │   ├── user.py
│   │   └── record.py
│   ├── schemas/             Pydantic 请求/响应模型
│   │   ├── user.py
│   │   └── record.py
│   ├── services/            业务逻辑
│   │   ├── predictor.py     ★ 模型推理核心
│   │   ├── auth.py          用户认证（JWT）
│   │   └── preprocess.py    图像预处理
│   └── routers/             路由
│       ├── auth.py          注册/登录
│       ├── predict.py       ★ 图像检测
│       └── records.py       历史记录
├── uploads/                 上传的原图
└── requirements.txt
```

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（含模型状态） |
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录（返回 JWT） |
| GET | `/api/auth/me` | 获取当前用户信息 |
| POST | `/api/predict` | **图像检测**（上传图 → 良恶性 + 置信度） |
| GET | `/api/records` | 检测历史列表 |
| GET | `/api/records/{id}` | 单条记录详情 |
| DELETE | `/api/records/{id}` | 删除记录 |
| GET | `/api/records/export` | 导出历史（CSV） |

## 模型说明

推理服务会**自动探测** models 目录下可用的模型文件，优先级：

1. `models_vE_r101_288/best.pt`（若方案E成功）
2. `models_v2_full/best.pt`（当前最佳 84.98%）
3. `models_vD_warmup/best.pt`
4. `models/best.pt`

checkpoint 里已保存 `arch` / `img_size` / `classes`，服务读取后自动构建对应结构，
无需手工配置。

## 医疗免责声明

本服务仅作为皮肤健康自检的辅助工具，检测结果仅供参考，不能替代专业医生的诊断。
