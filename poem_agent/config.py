# -*- coding: utf-8 -*-
"""
config.py —— 全局配置:模型、价格、预算、视频参数、路径

设计原则(对照手册):
1. 所有"可能要调"的数字都集中在这里,不散在代码里
2. 价格表是【估算值】,M0 的正确做法是跑几次后按真实账单校准(手册 cost.md 的用意)
3. 没有 SILICONFLOW_API_KEY 时整条链路自动降级,不报错不卡死
"""

import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# 从上层 f:\desktop\Poem\.env 加载(和 01_chat.py 同一套 key 管理)
load_dotenv(find_dotenv())

# ============ 路径 ============
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
CHECKPOINT_DB = ROOT / "output" / "checkpoints.sqlite"   # 断点续传数据库(手册 M1)

# ============ API key ============
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")   # 空 = 降级模式
KLING_API_KEY = os.environ.get("KLING_API_KEY", "")               # v2 预留:图生视频


def has_t2i() -> bool:
    """有没有真实文生图能力(没有就全走水墨字卡降级)"""
    return bool(SILICONFLOW_API_KEY)


def has_vlm() -> bool:
    """有没有真实 VLM 质检能力(没有就模拟通过,质检环不生效)"""
    return bool(SILICONFLOW_API_KEY)


# ============ 模型选型(手册的省钱版) ============
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"                          # 解析/分镜/路由都用它

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
T2I_MODEL = "Kwai-Kolors/Kolors"                          # 文生图:支持中文 prompt,便宜
VLM_MODEL = "Qwen/Qwen2.5-VL-32B-Instruct"                # 审图质检;想更省换 7B
T2I_SIZE = "960x1280"                                     # 竖版,后面 ffmpeg 会放大裁切到 1080x1920

# ============ 价格表(元,估算!跑通后按真实账单校准) ============
PRICE = {
    "llm_in_per_1m": 2.0,     # deepseek-chat 输入 元/百万token(以官网现价为准)
    "llm_out_per_1m": 8.0,    # deepseek-chat 输出
    "t2i_per_image": 0.10,    # Kolors 单张(以硅基流动现价为准)
    "vlm_per_call": 0.02,     # VLM 审一次图(按 token 计费,这里取典型值)
    "tts_per_line": 0.0,      # edge-tts 免费
}
BUDGET_PER_VIDEO = 2.0        # 单条视频预算上限(元);超了强制降级(手册 M4)

# ============ 质检反思环参数(手册 M3) ============
MAX_QC_RETRY = 2              # 质检不过最多改写重试次数,再败走降级
QC_MOOD_MIN = 3               # 氛围匹配分(1-5)低于此判不合格
PREMIUM_CANDIDATES = 2        # 名场面句生成几张候选图选优(成本路由的 premium 路径)

# ============ 视频参数 ============
VIDEO_W, VIDEO_H = 1080, 1920  # 竖版(短视频平台)
FPS = 30
LINE_PAD_SEC = 0.6             # 每句时长 = 吟诵音频 + 这个 padding
TITLE_CARD_SEC = 2.0           # 片头字卡时长

# ============ TTS ============
TTS_VOICE = "zh-CN-YunjianNeural"   # 男声,沉稳,适合吟诵;女声可换 zh-CN-XiaoxiaoNeural
TTS_RATE = "-25%"                   # 放慢语速,有"吟"的感觉

# ============ 字体(已确认本机存在) ============
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simkai.ttf",    # 楷体——诗词首选
    r"C:\Windows\Fonts\STKAITI.TTF",   # 华文楷体
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑保底
]
FONT_PATH = next((f for f in _FONT_CANDIDATES if Path(f).exists()), _FONT_CANDIDATES[-1])
