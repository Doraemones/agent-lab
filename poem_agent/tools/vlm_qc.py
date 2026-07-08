# -*- coding: utf-8 -*-
"""
vlm_qc.py —— VLM 审图质检(手册 M3 反思环的"眼睛")

⭐ 核心设计(面试第 16 问的标准答案,背下来):
质检判据必须【结构化】,不能让 VLM 裸打分——
  裸打分("这图配这句诗打几分?")会得到一堆 7 分 8 分,毫无区分度;
  正确做法是把判断拆成可核对的客观项:
    1. 逐项核对"必现意象清单"(生图 prompt 承诺过的)有没有画出来 → 硬判据
    2. 氛围匹配 1-5 分 → 软判据
    3. 具体问题描述 → 反馈给改写节点,形成闭环
  判定规则写在代码里而不是 prompt 里:missing>0 或 mood<QC_MOOD_MIN → 不合格。
  (VLM 也会误判——所以留 qc_history 全档,人工抽查就能发现,这是第 16 问后半段)

无 key 时返回 simulated=True 的"模拟通过",让链路可跑,但报告里会如实标注。
"""

import base64
import io
import json
import re
from pathlib import Path

import httpx
from PIL import Image

import config
from state import QCRecord


def _encode_image(path: str) -> str:
    """压到长边 1024 再转 base64:审图不需要原图分辨率,省 token 就是省钱"""
    img = Image.open(path).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def qc(image_path: str, line: str, must_have: list[str], attempt: int) -> tuple[QCRecord, float]:
    if not config.has_vlm():
        # 降级模式:没有"眼睛",只能模拟通过。simulated=True 会写进报告,不冒充真质检。
        return QCRecord(
            attempt=attempt, passed=True, present=list(must_have), missing=[],
            mood_score=0, problems="(无 VLM key,模拟通过)", simulated=True,
        ), 0.0

    instruction = f"""你是古诗配图的质检员。诗句:「{line}」
下面这张图是为这句诗生成的配图,要求画面中必须出现这些意象:{must_have}

逐项核对后,只输出一个 JSON 对象:
{{
  "present": [画面中确实出现的意象],
  "missing": [缺失或画错的意象],
  "mood_score": 画面氛围与诗句意境的匹配度整数1-5,
  "problems": "具体问题,一两句话。如出现现代物品/意象画错/构图问题,明确指出,方便改写提示词"
}}
注意:出现任何现代元素(现代家具/电灯/玻璃杯/现代建筑)都算严重问题,须在 problems 里点名。"""

    payload = {
        "model": config.VLM_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{_encode_image(image_path)}"}},
                {"type": "text", "text": instruction},
            ],
        }],
        "temperature": 0.1,          # 质检要稳定,低温
        "max_tokens": 400,
    }
    headers = {"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"}

    try:
        with httpx.Client(timeout=90) as client:
            r = client.post(f"{config.SILICONFLOW_BASE_URL}/chat/completions",
                            json=payload, headers=headers)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
    except Exception as e:
        # 质检工具自己挂了 ≠ 图不合格:放行但记录,避免"质检故障导致无限重试烧钱"
        print(f"    [vlm] 质检调用失败,放行:{type(e).__name__}: {e}", flush=True)
        return QCRecord(
            attempt=attempt, passed=True, present=[], missing=[],
            mood_score=0, problems=f"(VLM 调用失败,放行:{e})", simulated=True,
        ), 0.0

    missing = [str(x) for x in data.get("missing", [])]
    mood = int(data.get("mood_score", 3))
    # ⭐ 判定规则在代码里,不在模型嘴里:硬判据(意象缺失)+ 软判据(氛围分)
    passed = len(missing) == 0 and mood >= config.QC_MOOD_MIN
    return QCRecord(
        attempt=attempt, passed=passed,
        present=[str(x) for x in data.get("present", [])],
        missing=missing, mood_score=mood,
        problems=str(data.get("problems", "")), simulated=False,
    ), config.PRICE["vlm_per_call"]
