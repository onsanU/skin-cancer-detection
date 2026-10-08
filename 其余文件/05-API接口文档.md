# 皮肤癌图像检测系统 — API 接口文档

| 项目名称 | 皮肤癌图像检测系统 |
|---------|------------------|
| 文档版本 | V1.0.0 |
| 编制日期 | 2026-09-14 |
| 服务地址 | `http://127.0.0.1:8000` |
| 在线文档 | `http://127.0.0.1:8000/docs`（Swagger UI）|
| 接口风格 | RESTful |
| 数据格式 | JSON（文件上传为 multipart/form-data）|

---

## 一、通用说明

### 1.1 请求规范

| 项目 | 说明 |
|------|------|
| Base URL | `http://127.0.0.1:8000` |
| 内容类型 | `application/json`（除文件上传接口）|
| 编码 | UTF-8 |
| 认证方式 | Bearer Token（JWT），置于请求头 `Authorization: Bearer <token>` |

### 1.2 认证说明

| 接口类型 | 是否需要 Token |
|---------|--------------|
| 注册 / 登录 | ❌ 不需要 |
| 健康检查 / 服务信息 / 模型信息 / 阈值预设 | ❌ 不需要 |
| 图像检测（`/api/predict`）| 🔶 **可选**（游客可用，但不保存记录）|
| 历史记录相关 | ✅ 必需 |
| 当前用户信息 | ✅ 必需 |

**Token 获取方式**：调用注册或登录接口，响应中的 `token` 字段。

**Token 有效期**：7 天（604800 秒）。

**Token 格式**：`eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.<payload>.<signature>`（JWT HS256）

### 1.3 响应规范

**成功响应**：HTTP 200 + JSON 数据

**错误响应**：HTTP 4xx/5xx + 统一格式

```json
{
  "detail": "错误描述（中文）"
}
```

### 1.4 状态码约定

| 状态码 | 含义 | 典型场景 |
|--------|------|---------|
| 200 | 成功 | 正常返回 |
| 400 | 请求参数错误 | 格式不符、大小超限、用户名重复 |
| 401 | 未认证 / 认证失效 | 未带 Token、Token 过期、密码错误 |
| 403 | 无权限 | — |
| 404 | 资源不存在 | 记录 ID 不存在、图片不存在 |
| 422 | 参数校验失败 | 邮箱格式错误、字段缺失（FastAPI 自动）|
| 500 | 服务器内部错误 | 推理异常 |
| 503 | 服务不可用 | 模型未就绪 |

### 1.5 公共响应头

| 响应头 | 说明 |
|--------|------|
| `X-Process-Time-Ms` | 服务端处理耗时（毫秒）|

---

## 二、接口清单

| # | 方法 | 路径 | 说明 | 认证 |
|---|------|------|------|------|
| 1 | POST | `/api/auth/register` | 用户注册 | ❌ |
| 2 | POST | `/api/auth/login` | 用户登录 | ❌ |
| 3 | GET | `/api/auth/me` | 获取当前用户信息 | ✅ |
| 4 | POST | `/api/predict` | **皮肤病变图像检测** | 🔶 可选 |
| 5 | GET | `/api/image/{name}` | 获取上传的图片 | ❌ |
| 6 | GET | `/api/model/info` | 模型信息 | ❌ |
| 7 | GET | `/api/model/types` | 7 类病变类型定义 | ❌ |
| 8 | GET | `/api/thresholds` | 阈值预设列表 | ❌ |
| 9 | GET | `/api/records` | 检测历史列表 | ✅ |
| 10 | GET | `/api/records/stats` | 检测统计 | ✅ |
| 11 | GET | `/api/records/export` | 导出记录（CSV）| ✅ |
| 12 | GET | `/api/records/{record_id}` | 单条记录详情 | ✅ |
| 13 | DELETE | `/api/records/{record_id}` | 删除记录 | ✅ |
| 14 | GET | `/api/health` | 健康检查 | ❌ |
| 15 | GET | `/` | 服务信息 | ❌ |

### 2.1 管理后台接口（v1.1.0 新增）

> 认证列标 **👑** 表示需要**管理员**（`role=admin`）：未登录返回 **401**，非管理员返回 **403**。
> 管理后台界面：`http://127.0.0.1:8000/admin/`

| # | 方法 | 路径 | 说明 | 认证 |
|---|------|------|------|------|
| M1 | GET | `/admin/api/stats` | 数据看板统计 | 👑 |
| M2 | GET | `/admin/api/records` | 检测记录列表（分页/筛选/搜索） | 👑 |
| M3 | GET | `/admin/api/records/{id}` | 记录详情 | 👑 |
| M4 | DELETE | `/admin/api/records/{id}` | 删除记录（含磁盘图片） | 👑 |
| M5 | GET | `/admin/api/users` | 用户列表（分页/筛选/搜索） | 👑 |
| M6 | GET | `/admin/api/users/{id}` | 用户详情（含最近记录） | 👑 |
| M7 | POST | `/admin/api/users/{id}/role` | 调整角色（提权/降级） | 👑 |
| M8 | POST | `/admin/api/users/{id}/password` | 重置密码 | 👑 |
| M9 | POST | `/admin/api/users/{id}/active` | 启用/禁用账号 | 👑 |
| M10 | DELETE | `/admin/api/users/{id}/records` | 清空用户检测记录 | 👑 |
| M11 | GET | `/admin/api/system` | 系统状态 | 👑 |

**管理接口要点**：

- **M1 数据看板**：`total_users` / `total_records` / `malignant` / `benign` / `malignant_rate` /
  `today_records` / `today_users` / `avg_infer_ms` / `trend`（近7日）/ `top_users`（Top10）/ `model`（模型状态）
- **M2 记录列表**：查询参数 `limit`(1-200) / `offset` / `label`(benign|malignant) / `keyword`（文件名·用户名·备注模糊）/ `username`（精确）；非法 `label` → 400
- **M4 删除记录**：记录不存在时返回 `{"deleted": 0}` 而非报错（幂等友好）
- **M5 用户列表**：查询参数 `limit` / `offset` / `keyword` / `role`(user|admin)；返回含 `record_count` 与 `malignant_count`
- **M7 角色调整**：body `{"role": "admin"|"user"}`；**不能降级自己** → 400；**系统须保留至少一名管理员** → 400
- **M8 重置密码**：body `{"password": "..."}`，≥6 位否则 422；密码哈希不可逆，管理端无法查看明文
- **M9 账号状态**：body `{"is_active": true|false}`；**不能禁用自己** → 400
- **M11 系统状态**：服务运行时长 / `model` / `type_model` / `ensemble` / `database` / `storage`（磁盘+上传统计）/ `config`（ONNX、阈值预设、上传限制）

**管理接口鉴权示例**：

```bash
# 1. 管理员登录（默认账号 admin / <密码>，公网部署前请改密码）
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<密码>"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['token'])")

# 2. 调用管理接口
curl -s http://127.0.0.1:8000/admin/api/stats -H "Authorization: Bearer $TOKEN"

# 3. 未带 token → 401；普通用户 token → 403
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/admin/api/stats
```

---

## 三、接口详述

### 3.1 用户注册

**`POST /api/auth/register`**

**请求体**：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| username | string | ✅ | 3-32 字符 | 用户名 |
| email | string | ✅ | 邮箱格式 | 邮箱 |
| password | string | ✅ | 6-128 字符 | 密码 |
| full_name | string | ❌ | ≤64 字符 | 姓名/昵称 |

**请求示例**：

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testcat","email":"testcat@example.com","password":"miao123456","full_name":"测试猫咪"}'
```

**成功响应**（200）：

```json
{
  "message": "注册成功",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "testcat",
    "email": "testcat@example.com",
    "full_name": "测试猫咪",
    "created_at": "2026-09-14 14:39:08"
  }
}
```

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| 400 | 用户名至少3个字符 / 密码至少6个字符 / 用户名已被注册 / 邮箱已被注册 |
| 422 | 邮箱格式不正确 |

---

### 3.2 用户登录

**`POST /api/auth/login`**

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | ✅ | **用户名或邮箱** |
| password | string | ✅ | 密码 |

**请求示例**：

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testcat","password":"miao123456"}'
```

**成功响应**（200）：

```json
{
  "message": "登录成功",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "testcat",
    "email": "testcat@example.com",
    "full_name": "测试猫咪",
    "created_at": "2026-09-14 14:39:08"
  }
}
```

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| 401 | 用户名或密码错误 / 账号已被禁用 |

---

### 3.3 获取当前用户信息

**`GET /api/auth/me`** 🔒 需认证

**请求示例**：

```bash
curl http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer <token>"
```

**成功响应**（200）：

```json
{
  "user": {
    "id": 1,
    "username": "testcat",
    "email": "testcat@example.com",
    "full_name": "测试猫咪",
    "created_at": "2026-09-14 14:39:08"
  },
  "stats": {
    "total": 12,
    "malignant": 5,
    "benign": 7
  }
}
```

**错误响应**：401（未提供认证信息 / 登录已过期）

---

### 3.4 皮肤病变图像检测 ★ 核心接口

**`POST /api/predict`** 🔶 认证可选

**请求格式**：`multipart/form-data`

**请求参数**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| file | file | ✅ | — | 图像文件（JPG/PNG/BMP/WEBP，≤10MB）|
| threshold | float | ❌ | 0.5 | 恶性判定阈值（0.20-0.80）|
| note | string | ❌ | "" | 用户备注 |

**请求示例**：

```bash
curl -X POST http://127.0.0.1:8000/api/predict \
  -H "Authorization: Bearer <token>" \
  -F "file=@lesion.jpg" \
  -F "threshold=0.48" \
  -F "note=手臂内侧，发现2周"
```

**成功响应**（200）：

```json
{
  "record_id": 15,
  "result": {
    "label": "malignant",
    "label_cn": "恶性",
    "probability": 0.8729,
    "malignant_prob": 0.8729,
    "benign_prob": 0.1271,
    "threshold": 0.5,
    "infer_ms": 32.1
  },
  "advice": {
    "title": "检测结果显示倾向恶性",
    "level": "high",
    "text": "系统判定该病变图像的特征倾向恶性。这**不是诊断结论**，但建议您尽快到正规医院皮肤科就诊...",
    "actions": [
      "尽快预约皮肤科门诊（建议1-2周内）",
      "就诊时告知医生病变部位的发现时间与变化情况",
      "避免自行抓挠、挤压或使用刺激性药物",
      "注意防晒，避免病变部位暴晒"
    ]
  },
  "image_url": "/api/image/u1_20260914_144048_a3f2b1c9.jpg",
  "saved": true,
  "disclaimer": "⚠️ 医疗免责声明：本系统仅作为皮肤健康自检的辅助工具..."
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `record_id` | 记录 ID；游客或保存失败时为 `null` |
| `result.probability` | 判定类别的置信度（良性时=良性概率）|
| `result.malignant_prob` | 恶性概率（始终为该值）|
| `result.threshold` | 本次判定所用阈值 |
| `result.infer_ms` | 推理耗时（毫秒）|
| `advice.level` | `high`（恶性）/ `low`（良性）|
| `saved` | 是否已保存到历史记录 |

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| 400 | 不支持的图片格式 / 图片过大（限制10MB）|
| 503 | 模型未就绪 |
| 500 | 推理失败 |

---

### 3.5 获取上传的图片

**`GET /api/image/{name}`**

**路径参数**：

| 参数 | 说明 |
|------|------|
| name | 存储文件名（如 `u1_20260914_144048_a3f2b1c9.jpg`）|

**响应**：图片二进制流（`Content-Type: image/jpeg` 等）

**安全设计**：使用 `os.path.basename()` 过滤路径穿越攻击（如 `../../etc/passwd`）。

**错误响应**：404（图片不存在）

---

### 3.6 模型信息

**`GET /api/model/info`**

**成功响应**（200）：

```json
{
  "model": {
    "ready": true,
    "backend": "onnx-int8",
    "model_path": ".../models_compressed/model_int8.onnx",
    "arch": "resnet50(onnx-int8)",
    "img_size": 224,
    "classes": ["benign", "malignant"],
    "device": "cpu (onnxruntime)",
    "load_time_s": 0.222,
    "load_error": "",
    "infer_count": 15,
    "avg_infer_ms": 31.5
  },
  "disclaimer": "⚠️ 医疗免责声明..."
}
```

---

### 3.7 阈值预设列表

**`GET /api/thresholds`**

**成功响应**（200）：

```json
{
  "presets": {
    "screening": {
      "name": "筛查模式",
      "value": 0.20,
      "desc": "优先不漏诊，恶性召回 95.8%，漏诊率 4.2%，适合初步筛查"
    },
    "balanced": {
      "name": "平衡模式",
      "value": 0.5,
      "desc": "准确率与召回兼顾，准确率 85.0%，恶性召回 89.0%（默认）"
    },
    "accurate": {
      "name": "精确模式",
      "value": 0.48,
      "desc": "约登指数最优，恶性精确率 85.3%，适合作为确诊参考"
    }
  },
  "default": 0.5,
  "note": "阈值越低越敏感（恶性召回高、漏诊少），代价是误报增多"
}
```

---

### 3.8 检测历史列表

**`GET /api/records`** 🔒 需认证

**查询参数**：

| 参数 | 类型 | 默认 | 约束 | 说明 |
|------|------|------|------|------|
| limit | int | 20 | 1-200 | 每页数量 |
| offset | int | 0 | ≥0 | 偏移量 |
| label | string | — | benign/malignant | 按结果筛选 |

**请求示例**：

```bash
curl "http://127.0.0.1:8000/api/records?limit=12&offset=0&label=malignant" \
  -H "Authorization: Bearer <token>"
```

**成功响应**（200）：

```json
{
  "total": 6,
  "limit": 12,
  "offset": 0,
  "items": [
    {
      "id": 6,
      "filename": "ISIC_0024402.jpg",
      "label": "benign",
      "label_cn": "良性",
      "probability": 0.9618,
      "malignant_prob": 0.0382,
      "benign_prob": 0.9618,
      "threshold": 0.5,
      "infer_ms": 31.0,
      "note": "e2e测试",
      "created_at": "2026-09-14 14:40:49",
      "image_url": "/api/image/u1_20260914_144049_xxxx.jpg"
    }
  ]
}
```

---

### 3.9 检测统计

**`GET /api/records/stats`** 🔒 需认证

**成功响应**（200）：

```json
{
  "total": 12,
  "malignant": 5,
  "benign": 7
}
```

---

### 3.10 导出检测记录（CSV）

**`GET /api/records/export`** 🔒 需认证

**响应**：CSV 文件流

```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="skin_cancer_records_20260914_153012.csv"
```

**CSV 内容示例**（带 BOM，Excel 打开中文不乱码）：

```csv
ID,文件名,检测结果,置信度,恶性概率,良性概率,判定阈值,推理耗时(ms),备注,检测时间
6,ISIC_0024402.jpg,良性,0.9618,0.0382,0.9618,0.5,31.0,e2e测试,2026-09-14 14:40:49
```

**说明**：导出上限 10000 条记录。

---

### 3.11 单条记录详情

**`GET /api/records/{record_id}`** 🔒 需认证

**路径参数**：

| 参数 | 说明 |
|------|------|
| record_id | 记录 ID |

**成功响应**（200）：

```json
{
  "id": 6,
  "filename": "ISIC_0024402.jpg",
  "label": "benign",
  "label_cn": "良性",
  "probability": 0.9618,
  "malignant_prob": 0.0382,
  "benign_prob": 0.9618,
  "threshold": 0.5,
  "infer_ms": 31.0,
  "note": "e2e测试",
  "created_at": "2026-09-14 14:40:49",
  "image_url": "/api/image/u1_20260914_144049_xxxx.jpg",
  "advice": {
    "title": "检测结果显示倾向良性",
    "level": "low",
    "text": "...",
    "actions": ["..."]
  },
  "disclaimer": "⚠️ 医疗免责声明..."
}
```

**权限说明**：只能查询属于自己的记录（SQL 层强制 `user_id` 过滤），返回 404 而非 403（避免暴露记录是否存在）。

---

### 3.12 删除记录

**`DELETE /api/records/{record_id}`** 🔒 需认证

**成功响应**（200）：

```json
{
  "message": "删除成功",
  "id": 6
}
```

**副作用**：同时删除磁盘上的原始图片文件。

**错误响应**：404（记录不存在）

---

### 3.13 健康检查

**`GET /api/health`**

**成功响应**（200）：

```json
{
  "status": "ok",
  "service": "皮肤癌图像检测系统",
  "version": "1.0.0",
  "model": {
    "ready": true,
    "backend": "onnx-int8",
    "arch": "resnet50(onnx-int8)",
    "img_size": 224,
    "classes": ["benign", "malignant"],
    "device": "cpu (onnxruntime)",
    "load_time_s": 0.222,
    "load_error": "",
    "infer_count": 15,
    "avg_infer_ms": 31.5
  },
  "disclaimer": "⚠️ 医疗免责声明..."
}
```

**监控价值**：
- `model.ready`：模型是否就绪（服务降级判断）
- `model.load_error`：加载失败原因
- `model.avg_infer_ms`：平均推理性能
- `model.infer_count`：累计推理次数

---

### 3.14 服务信息

**`GET /`**

**成功响应**（200）：

```json
{
  "service": "皮肤癌图像检测系统 API",
  "docs": "/docs",
  "health": "/api/health",
  "message": "喵~ 服务运行中 (=^･ω･^=)"
}
```

---

## 四、完整调用流程示例

### 4.1 完整用户流程（curl）

```bash
BASE=http://127.0.0.1:8000

# 1. 注册（或登录）
TOKEN=$(curl -s -X POST $BASE/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"alice123"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")

# 2. 上传图像检测（精确模式，默认阈值0.48）
curl -X POST $BASE/api/predict \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/lesion.jpg" \
  -F "threshold=0.48" \
  -F "note=复查"

# 3. 查询历史记录
curl "$BASE/api/records?limit=10" -H "Authorization: Bearer $TOKEN"

# 4. 查看统计
curl "$BASE/api/records/stats" -H "Authorization: Bearer $TOKEN"

# 5. 导出 CSV
curl "$BASE/api/records/export" -H "Authorization: Bearer $TOKEN" -o records.csv
```

### 4.2 前端调用（JavaScript）

```javascript
import { api, tokenStore } from './api/client'

// 注册
const { token, user } = await api.post('/auth/register', {
  username: 'alice', email: 'alice@example.com', password: 'alice123'
}).then(r => r.data)
tokenStore.set(token)

// 检测（FormData 自动处理 multipart）
const form = new FormData()
form.append('file', fileInput.files[0])
form.append('threshold', '0.48')
form.append('note', '手臂内侧')
const result = await api.post('/predict', form).then(r => r.data)
console.log(result.result.label_cn)  // "恶性"

// 历史记录
const records = await api.get('/records', { params: { limit: 12 } }).then(r => r.data)
```

---

## 五、错误处理建议

| 场景 | 建议处理 |
|------|---------|
| 401 未认证 | 清除本地 Token，跳转登录页 |
| 503 模型未就绪 | 提示"服务正在初始化，请稍后重试" |
| 400 参数错误 | 直接展示 `detail` 中的中文提示 |
| 网络超时 | 提示重试，检查服务是否启动 |

**前端统一错误处理**（已实现于 `api/client.js`）：

```javascript
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      tokenStore.clear()      // 认证失效自动清理
    }
    return Promise.reject(new Error(err.response?.data?.detail || err.message))
  }
)
```

---

## 六、性能指标

| 接口 | 平均响应时间 | 说明 |
|------|------------|------|
| `/api/health` | < 5ms | 内存读取 |
| `/api/auth/login` | ~50ms | PBKDF2 12万次迭代 |
| `/api/predict` | ~35ms | 含推理 31.5ms（ONNX INT8）|
| `/api/records` | < 10ms | 索引查询 |
| `/api/records/export` | ~30ms | 1000 条以内 |

---

## 七、接口测试

已实现的端到端测试覆盖：

| 测试项 | 结果 |
|--------|------|
| 用户注册 | ✅ |
| 用户登录 | ✅ |
| 获取用户信息 | ✅ |
| 图像检测（真实数据 6 张）| ✅ 5/6 正确 |
| 记录自动保存 | ✅ |
| 历史记录查询 | ✅ |
| 按结果筛选 | ✅ |
| 检测统计 | ✅ |
| CSV 导出 | ✅ |
| 删除记录 | ✅ |
| 阈值参数生效 | ✅ |
| 健康检查 | ✅ |

详细测试报告见《05-测试报告.md》。
