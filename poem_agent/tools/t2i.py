# -*- coding: utf-8 -*-
"""
t2i.py —— 硅基流动 Kolors 文生图(手册选型:低价、支持中文 prompt)

裸 httpx 调 REST 接口,不套 SDK——你能看到一次文生图请求的完整样子。
容错策略(面试题"工具调用失败怎么处理"):
  - 没配 key         → 返回 None,由上游决定降级(不在工具层擅自决定)
  - 请求失败/超时    → 重试 1 次,再失败返回 None + 打印原因
返回值统一 (图片路径 | None, 花费)。
"""

import time
from pathlib import Path

import httpx

import config


def generate(prompt: str, out_path: str | Path) -> tuple[str | None, float]:
    if not config.has_t2i():
        return None, 0.0

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": config.T2I_MODEL,
        "prompt": prompt,
        "image_size": config.T2I_SIZE,        # 960x1280 竖版,后面 ffmpeg 再放大裁切
        "batch_size": 1,
        "num_inference_steps": 20,            # 20 步够用,步数=时间=钱
        "guidance_scale": 7.5,                # 提示词服从度,7-8 是常规区间
    }
    headers = {"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"}

    for attempt in (1, 2):                    # 最多试 2 次
        try:
            with httpx.Client(timeout=120) as client:
                r = client.post(
                    f"{config.SILICONFLOW_BASE_URL}/images/generations",
                    json=payload, headers=headers,
                )
                r.raise_for_status()
                url = r.json()["images"][0]["url"]     # 返回的是临时下载链接
                img = client.get(url, timeout=120)
                img.raise_for_status()
                out_path.write_bytes(img.content)
            return str(out_path), config.PRICE["t2i_per_image"]
        except Exception as e:
            print(f"    [t2i] 第 {attempt} 次生图失败:{type(e).__name__}: {e}", flush=True)
            if attempt == 1:
                time.sleep(2)                 # 歇口气再试,可能是瞬时限流
    return None, 0.0
