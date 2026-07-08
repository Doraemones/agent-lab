# -*- coding: utf-8 -*-
"""
tts.py —— edge-tts 逐句吟诵(免费,手册起步选型;进阶换 CosyVoice)

教学点:
- edge-tts 是 async 库,这里用 asyncio.run 包成同步接口,graph 节点里好调
- 音频时长决定视频每句的时长,所以合成完立刻 ffprobe 量出真实时长
- 网络失败的兜底:生成等长静音,让整条流水线"缺声不断片"(工具失败处理)
"""

import asyncio
from pathlib import Path

import edge_tts

import config
from tools.video import probe_duration, make_silence


def synth(text: str, out_path: str | Path) -> tuple[str, float]:
    """合成一句吟诵。返回 (音频路径, 时长秒)。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run():
        comm = edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE)
        await comm.save(str(out_path))

    try:
        asyncio.run(_run())
        return str(out_path), probe_duration(out_path)
    except Exception as e:
        print(f"    [tts] 合成失败,用静音顶上:{type(e).__name__}: {e}", flush=True)
        silent = out_path.with_suffix(".silent.mp3")
        make_silence(silent, 2.5)
        return str(silent), 2.5
