#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置：路径、模型、上传限制等"""

import os

# ---------- 目录 ----------
# config.py 位于 <proj>/backend/app/config.py
APP_DIR = os.path.dirname(os.path.abspath(__file__))          # <proj>/backend/app
BACKEND_DIR = os.path.dirname(APP_DIR)                        # <proj>/backend
PROJ_ROOT = os.path.dirname(BACKEND_DIR)                      # <proj>
MODELS_DIR = PROJ_ROOT      # 各实验目录(models_v2_full 等)直接位于项目根下
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")
DB_PATH = os.path.join(BACKEND_DIR, "skin_cancer.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================================================
#  数据库后端（双模式，2026-09-15 新增）
# ------------------------------------------------------------
#  DB_BACKEND = "sqlite"  → 用 backend/skin_cancer.db（零配置，默认，答辩演示首选）
#  DB_BACKEND = "mysql"   → 用 Windows 侧 MySQL 8.0.29 的 skin_cancer 库
#                           （独立库+独立账号，与医小喵 yixiaomiao 库完全隔离）
#
#  切换方式（任选）：
#    ① 环境变量:  SKIN_DB_BACKEND=mysql bash start.sh
#    ② 直接改下面的默认值
# ============================================================
DB_BACKEND = os.environ.get("SKIN_DB_BACKEND", "sqlite").strip().lower()

# ---------- MySQL 连接参数 ----------
# 后端跑在 WSL，MySQL 跑在 Windows → 必须用 WSL 网关 IP（不是 localhost）
# 取法: ip route | grep default | awk '{print $3}'   （实测 172.30.160.1，换网络会变）
def _wsl_gateway_ip() -> str:
    """自动探测 WSL 宿主（Windows）IP，失败回退 127.0.0.1（服务跑在 Windows 时可用）"""
    env_ip = os.environ.get("SKIN_DB_HOST")
    if env_ip:
        return env_ip
    try:
        import subprocess
        out = subprocess.run(
            "ip route | grep default | awk '{print $3}'",
            shell=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip().split("\n")[0]
        if out:
            return out
    except Exception:
        pass
    return "127.0.0.1"

MYSQL_HOST = _wsl_gateway_ip()
MYSQL_PORT = int(os.environ.get("SKIN_DB_PORT", "3306"))
MYSQL_USER = os.environ.get("SKIN_DB_USER", "skin_cancer")
# ⚠️ 密码优先走环境变量；此处默认值为本地学习环境用（生产务必改掉）
MYSQL_PASSWORD = os.environ.get("SKIN_DB_PASSWORD", "skc123456")
MYSQL_DATABASE = os.environ.get("SKIN_DB_NAME", "skin_cancer")
MYSQL_CHARSET = "utf8mb4"


# ---------- 模型候选（按优先级） ----------
# 注意：训练中的实验目录(如 models_vE_r101_288)会不断覆盖 best.pt，
# 服务重启时可能加载到未完成的中间产物。正式版应按需调整顺序。
MODEL_CANDIDATES = [
    ("models_v2_full", "best.pt"),        # 当前最佳: acc 84.98% AUC 0.9162（部署用）
    ("models_vE_r101_288", "best.pt"),    # ResNet101-288: acc 84.98% AUC 0.9187（AUC最高）
    # ("models_vD_warmup", "best.pt"),    # warmup 实验: acc 83.57% —— 2026-09-17 已清理（权重删除）
]

# 推理设备
DEVICE = "cuda"

# ---------- 推理后端 ----------
# True  : 优先用 ONNX（models_compressed/model_int8.onnx，体积 4x 小）
# False : 用 PyTorch checkpoint（精度略高，无需 onnxruntime）
USE_ONNX = True
ONNX_MODEL_PATH = os.path.join(PROJ_ROOT, "models_compressed", "model_int8.onnx")
ONNX_THREADS = 4

# ---------- 7 类病变类型推理（辅助功能）----------
# True  : 主结论之外，额外给出"可能是哪种病变"的参考信息
# False : 只做二分类，不加载 7 类模型（省内存）
ENABLE_TYPE_PREDICT = True
TYPE_MODEL_CANDIDATES = [
    ("models_7class_r50", "best.pt"),     # 7 类分类: acc 74.32% / AUC 0.9258
]
# 7 类模型的 ONNX 加速路径（可选，体积 3.93x 小、CPU 推理）
# True  : 优先用 ONNX INT8（22.9MB），失败回退 PyTorch
# False : 只用 PyTorch checkpoint（精度略高）
TYPE_USE_ONNX = True
TYPE_ONNX_PATH = os.path.join(PROJ_ROOT, "models_compressed_7class", "model_int8.onnx")
# 7 类模型实测准确率（前端用于标注可信度，勿夸大）
TYPE_MODEL_ACCURACY = 0.7432
TYPE_DISCLAIMER = (
    "类型判断为参考信息，准确性（约 74%）低于良恶性判断（约 85%），"
    "不可作为诊断依据。具体类型需专业医生结合临床与病理确认。"
)

# ---------- 集成推理（提升准确率）----------
# True  : 用多个二分类模型概率平均（acc 85.45% / AUC 0.9287，推荐）
# False : 只用单个模型（acc 84.98%，但恶性召回更高 88.98%）
ENABLE_ENSEMBLE = True
# 参与集成的模型（按顺序，均为二分类模型）
# 格式: (目录, 文件名[, 权重])
#   · 权重可省略，省略时默认 1.0（即等权平均，与历史行为一致）
#   · 权重是相对值，实际按 w/sum(w) 归一化
ENSEMBLE_MODELS = [
    ("models_vE_r101_288", "best.pt", 1.0),        # R101/288: acc 84.98% AUC 0.9187  (权重1)
    ("models_mix_cutmix_long", "best.pt", 1.0),    # ConvNeXt-T/288 + Focal + CutMix 60轮: acc 85.92% (权重1)
]
# 集成模式推荐阈值（经 val 标定 + src/ensemble_multiarch.py 权重搜索得出）
#   该组合实测: test 213 张 acc 86.38% / 恶性召回 91.53% / AUC 0.9276  ★历史最优
#   对比上一版(R101×2 + convnext_focal×1): acc 85.45% / 召回 88.98% / AUC 0.9242
#   → 准确率 +0.93%、恶性召回 +4.24%（CutMix 训练的新模型全面替代了旧 ConvNeXt）
#   历史沿革: 等权(R50+R101) 85.45%/87.29% → R101×2+ConvNeXt 85.45%/88.98% → 本版 86.38%/91.53%
ENSEMBLE_THRESHOLD = 0.48

# ---------- 上传限制 ----------
MAX_UPLOAD_MB = 10
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/bmp", "image/webp"}

# ---------- 类别 ----------
CLASSES = ["benign", "malignant"]
CLASS_CN = {"benign": "良性", "malignant": "恶性"}

# ---------- 判定阈值 ----------
# 恶性概率 >= 该值判为恶性。
# 经阈值调优实验得到推荐操作点（集成与单模型分别扫描，见 src/*threshold_tuning.py）：
#
#   【集成模式（默认，ENSEMBLE_THRESHOLD=0.48）】— 2026-09-17 换用 CutMix 新模型后重新标定
#     val 326 张标定，test 213 张报成绩（严格 val 标定 / test 只报成绩）
#     0.48  精确模式：准确率 86.38%，恶性召回 91.53%（默认，准确率最高）
#     0.33  平衡模式：准确率 83.10%，恶性召回 95.76%
#     0.20  筛查模式：准确率 78.87%，恶性召回 99.15%（val 上漏诊率 0%）
#
#   【单模型模式（ENABLE_ENSEMBLE=False，MALIGNANT_THRESHOLD=0.50）】
#     0.32  筛查模式：恶性召回 95.76%，漏诊率仅 4.24%
#     0.50  平衡模式：准确率 84.98%，恶性召回 88.98%（默认）
MALIGNANT_THRESHOLD = 0.50

# 预设工作模式（前端可切换）
# ---------- 阈值预设 ----------
# 三档单调递增：筛查(激进,召回优先) < 平衡(中间) < 精确(保守,准确率优先)
# ⚠️ 数值经 val 集标定（阈值只在 val 上定，test 仅用于报成绩）
#    当前模型: 等权集成 R101 + ConvNeXt-CutMix (acc 86.38% / 召回 91.53% / AUC 0.9276)
#    详见 docs/threshold_v3_mix.json
THRESHOLD_PRESETS = {
    "screening": {
        "name": "筛查模式",
        "value": 0.20,
        "desc": "优先不漏诊：val 漏诊率 0%，适合初步自查与大规模筛查",
    },
    "balanced": {
        "name": "平衡模式",
        "value": 0.33,
        "desc": "准确率与召回兼顾：恶性召回 95.8%，适合日常使用",
    },
    "accurate": {
        "name": "精确模式",
        "value": 0.48,
        "desc": "准确率最高：test 准确率 86.38%，判定更保守，被判为恶性时可信度更高",
    },
}

# ---------- 安全 ----------
SECRET_KEY = os.environ.get("SKIN_SECRET_KEY", "skin-cancer-dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7      # 7天

# ---------- 健康建议 ----------
# 结构：① 按良恶性给基础建议  ② 若 7 类类型参考可用，再按 top1 类型给【细分补充】
#   细分建议只做「就医紧迫性 / 关注点」的差异化，不替代医生诊断
ADVICE = {
    "malignant": {
        "title": "检测结果显示倾向恶性",
        "level": "high",
        "text": (
            "系统判定该病变图像的特征倾向恶性。这「不是诊断结论」，但建议您尽快到正规医院"
            "皮肤科就诊，由专业医生进行皮肤镜检查或活检以明确诊断。"
            "早期发现和治疗的预后通常较好，请不要过度焦虑，但务必重视。"
        ),
        "actions": [
            "尽快预约皮肤科门诊（建议1-2周内）",
            "就诊时告知医生病变部位的发现时间与变化情况",
            "避免自行抓挠、挤压或使用刺激性药物",
            "注意防晒，避免病变部位暴晒",
        ],
    },
    "benign": {
        "title": "检测结果显示倾向良性",
        "level": "low",
        "text": (
            "系统判定该病变图像的特征倾向良性。这「不是诊断结论」，"
            "建议您继续观察该部位的变化情况。"
        ),
        "actions": [
            "定期自查该部位（建议每月一次），留意大小、形状、颜色变化",
            "若出现快速增大、颜色变深、边缘不规则、破溃出血，请及时就医",
            "日常做好防晒，减少紫外线暴露",
            "有皮肤癌家族史者建议每年做一次专业皮肤检查",
        ],
    },
}

# 7 类病变的细分建议（当类型参考可用时叠加到基础建议之上）
#   字段: urgency=就医紧迫性 / focus=关注要点 / actions=该类型专属补充建议
TYPE_ADVICE = {
    "mel": {
        "name": "黑色素瘤",
        "urgency": "高度关注",
        "focus": "恶性程度高、可能发生转移，尽早明确诊断非常关键",
        "actions": [
            "尽快（建议1-2周内）到皮肤科就诊，明确是否需要活检",
            "不要自行处理或观察等待，黑色素瘤早诊早治预后差异很大",
            "如病变近期出现增大、颜色不均、边缘不规则、破溃出血，请立即就医",
        ],
    },
    "bcc": {
        "name": "基底细胞癌",
        "urgency": "需要就诊",
        "focus": "转移风险低，但会局部侵犯周围组织，及时处理预后通常很好",
        "actions": [
            "建议到皮肤科就诊，医生可能建议手术切除或其它局部治疗",
            "不必过度焦虑：基底细胞癌生长缓慢、极少转移",
            "避免反复摩擦或刺激该部位，注意防晒",
        ],
    },
    "akiec": {
        "name": "光化性角化 / 原位鳞癌",
        "urgency": "需要就诊",
        "focus": "属癌前病变或早期原位癌，及时处理可阻断进展",
        "actions": [
            "建议到皮肤科就诊评估，医生可能建议冷冻、外用药物或光动力治疗",
            "该病变与长期紫外线暴露相关，日常需严格防晒",
            "定期复查，留意是否出现增厚、破溃等变化",
        ],
    },
    "scc": {
        "name": "鳞状细胞癌",
        "urgency": "需要就诊",
        "focus": "具有一定转移风险，建议尽早明确诊断",
        "actions": [
            "尽快到皮肤科就诊，评估是否需要活检与切除",
            "避免自行用药或抓挠刺激病变部位",
        ],
    },
    "nv": {
        "name": "黑色素细胞痣",
        "urgency": "常规观察",
        "focus": "绝大多数为良性，重点是持续观察其变化",
        "actions": [
            "按「ABCDE 法则」自查：不对称、边缘不规则、颜色不均、直径>6mm、近期变化",
            "如出现上述任一变化，请及时就医",
            "避免反复摩擦、抓挠或不当点痣",
        ],
    },
    "bkl": {
        "name": "良性角化",
        "urgency": "常规观察",
        "focus": "属良性病变，通常无需特殊处理",
        "actions": [
            "一般无需治疗；若影响外观或有刺激症状，可到皮肤科咨询处理",
            "如短期内明显增大或破溃，建议就诊",
        ],
    },
    "df": {
        "name": "皮肤纤维瘤",
        "urgency": "常规观察",
        "focus": "良性结节，通常无需处理",
        "actions": [
            "一般无需治疗，观察即可",
            "若持续增大或出现疼痛、破溃，建议到皮肤科就诊",
        ],
    },
    "vasc": {
        "name": "血管性病变",
        "urgency": "常规观察",
        "focus": "多为良性（如樱桃状血管瘤），通常无需处理",
        "actions": [
            "一般无需治疗；若短期内快速增大、出血或颜色明显改变，建议就诊",
            "避免挤压或自行挑破",
        ],
    },
}

# 类型参考的免责说明（前端在细分建议旁展示）
TYPE_ADVICE_DISCLAIMER = (
    "以上类型提示为模型的参考判断，准确性低于良恶性主判定，"
    "不构成诊断依据，请以医生面诊结果为准。"
)

# 病变部位选项（前端下拉；size_hint 用于提示该部位常见情况）
#   知识数据来源: backend/app/data/location_knowledge.json（HAM10000 统计）
LOCATION_OPTIONS = [
    {"key": "face",    "label": "面部 / 耳 / 鼻"},
    {"key": "scalp",   "label": "头皮 / 颈部"},
    {"key": "trunk",   "label": "躯干 / 胸 / 腹 / 背"},
    {"key": "arm",     "label": "上肢 / 手"},
    {"key": "leg",     "label": "下肢 / 足"},
    {"key": "genital", "label": "生殖器部位"},
    {"key": "unknown", "label": "不便说明"},
]

LOCATION_DISCLAIMER = (
    "部位参考为公开数据集的群体统计，仅供科普参考，"
    "个体情况请以医生面诊为准。"
)

DISCLAIMER = (
    "⚠️ 医疗免责声明：本系统仅作为皮肤健康自检的辅助工具，检测结果由AI模型生成，"
    "仅供参考，不构成医疗诊断，不能替代专业医生的诊断与治疗。"
    "如有任何疑虑或不适，请及时就医咨询专业医生。"
)

# ---------- Grad-CAM 可解释性 ----------
# 热力图叠加的透明度（0=只看原图，1=只看热力图）
CAM_ALPHA = 0.45
# 高斯平滑核相对图幅的比例（消除低分辨率特征图上采样产生的方块伪影）
CAM_SMOOTH_RATIO = 0.06
CAM_DISCLAIMER = (
    "⚠️ 热力图说明：颜色越暖（琥珀/橙红）表示模型在做判断时对该区域的关注度越高，"
    "颜色越冷（浅蓝）表示关注度越低。热力图反映的是「模型的注意力分布」，"
    "不等同于病灶的实际范围或医生的诊断依据，仅供理解模型行为使用。"
)
