# -*- coding: utf-8 -*-
"""
video.py —— ffmpeg 胶水层:运镜 / 字幕 / 音画合成 / 拼接

⚠ 这是全项目"最不 AI、最工程"的 40%,你手搓时最容易卡的就是这里。
   每个参数为什么这么写都注释了,建议逐条对照 ffmpeg 文档消化。

三个关键坑(Windows 特供):
1. drawtext 的字体路径:filter 语法里 ':' 是参数分隔符,所以 C:/Windows/...
   必须转义成 C\\:/Windows/...,否则报 "Unable to parse option value"
2. 中文字幕别直接塞 text= 参数(引号转义地狱),写进 UTF-8 文本文件用 textfile= 读
3. 所有片段的编码参数(分辨率/帧率/像素格式/音频采样率/声道数)必须完全一致,
   拼接才能用 -c copy 不重编码;差一项 concat 就出鬼畜或黑屏
"""

import subprocess
from pathlib import Path

import config

W, H, FPS = config.VIDEO_W, config.VIDEO_H, config.FPS

# 编码参数统一定义,make_clip / make_silent_clip 共用 → 保证可 -c copy 拼接
_ENC = [
    "-c:v", "libx264", "-preset", "medium", "-crf", "20",   # crf 20:画质好且体积可接受
    "-pix_fmt", "yuv420p",                                  # 播放器兼容性(不加有些手机黑屏)
    "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
    "-r", str(FPS),
]


def _run(cmd: list[str]):
    """跑 ffmpeg/ffprobe,失败时抛出 stderr 尾部(ffmpeg 的报错都在最后几行)"""
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = "\n".join((p.stderr or "").strip().splitlines()[-8:])
        raise RuntimeError(f"命令失败: {cmd[0]} ...\n{tail}")
    return p


def probe_duration(path: str | Path) -> float:
    """ffprobe 量媒体时长(秒)"""
    p = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", str(path)])
    return float(p.stdout.strip())


def make_silence(out_path: str | Path, duration: float):
    """生成一段静音 mp3(TTS 失败时的兜底)"""
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
          "-t", f"{duration}", "-q:a", "9", str(out_path)])


def _ff_escape(path: str | Path) -> str:
    """路径转成 filter 语法安全形式:反斜杠→斜杠,冒号加转义(坑 1)"""
    return str(path).replace("\\", "/").replace(":", "\\:")


def _zoompan(camera: str, frames: int) -> str:
    """
    Ken Burns 运镜三式(按句子情感选,parse_poem 节点决定):
      in  缓推:镜头慢慢凑近 → 聚焦、深情(思念/凝视类句子)
      out 缓拉:慢慢退远 → 释然、收束(常用于末句)
      pan 平移:横向扫过 → 叙事、空间展开(写景句)
    先把源图放大到 2 倍目标尺寸再 zoompan,否则亚像素采样会抖(经典 jitter 坑)。
    zoompan 的 on = 当前输出帧号,用 on/总帧数 做 0→1 的进度插值。
    """
    scale = f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2}"
    center = "x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
    if camera == "out":
        z = f"z='1.12-0.12*on/{frames}'"
        move = center
    elif camera == "pan":
        z = "z='1.10'"
        move = f"x='(iw-iw/zoom)*on/{frames}':y='(ih-ih/zoom)/2'"
    else:  # "in"
        z = f"z='1+0.12*on/{frames}'"
        move = center
    return f"{scale},zoompan={z}:{move}:d={frames}:s={W}x{H}:fps={FPS}"


def make_clip(image: str, audio: str, text: str, out_path: str | Path,
              duration: float, camera: str = "in") -> str:
    """
    单句成片:静态图 + 运镜 + 楷体字幕 + 吟诵音频。
    duration = 音频时长 + padding(调用方算好传进来)
    """
    out_path = Path(out_path)
    frames = int(duration * FPS)

    # 坑 2:中文字幕写进 UTF-8 文件,drawtext 用 textfile= 读
    textfile = out_path.with_suffix(".txt")
    textfile.write_text(text, encoding="utf-8")

    fontsize = 96 if len(text) <= 5 else 84          # 五言大一点,七言收一点
    drawtext = (
        f"drawtext=fontfile='{_ff_escape(config.FONT_PATH)}'"
        f":textfile='{_ff_escape(textfile)}'"
        f":fontsize={fontsize}:fontcolor=white"
        f":borderw=4:bordercolor=black@0.55"          # 黑描边,浅色画面上也读得清
        f":x=(w-text_w)/2:y=h-360"                    # 底部居中,留出平台 UI 安全区
    )
    fade = f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(duration-0.45, 0):.2f}:d=0.45"

    vf = f"[0:v]{_zoompan(camera, frames)},{drawtext},{fade},format=yuv420p[v]"
    af = f"[1:a]apad=whole_dur={duration},aresample=44100[a]"   # 音频不够长就补静音到齐

    _run(["ffmpeg", "-y",
          "-loop", "1", "-i", str(image),             # 图片循环成视频流
          "-i", str(audio),
          "-filter_complex", f"{vf};{af}",
          "-map", "[v]", "-map", "[a]",
          "-t", f"{duration:.3f}",                    # 精确截到目标时长
          *_ENC, str(out_path)])
    return str(out_path)


def make_silent_clip(image: str, out_path: str | Path, duration: float) -> str:
    """无声片段(片头标题字卡):图 + 淡入淡出 + 静音轨(有音轨才能和其他片段 concat)"""
    out_path = Path(out_path)
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(duration-0.45,0):.2f}:d=0.45,"
          f"format=yuv420p[v]")
    _run(["ffmpeg", "-y",
          "-loop", "1", "-i", str(image),
          "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
          "-filter_complex", vf,
          "-map", "[v]", "-map", "1:a",
          "-t", f"{duration:.3f}",
          *_ENC, str(out_path)])
    return str(out_path)


def concat(clips: list[str], out_path: str | Path) -> str:
    """
    concat demuxer 无损拼接(坑 3:全部片段编码参数一致才能 -c copy)。
    列表文件里用正斜杠路径 + 单引号包裹,-safe 0 允许绝对路径。
    """
    out_path = Path(out_path)
    list_file = out_path.with_suffix(".list.txt")
    list_file.write_text(
        "\n".join(f"file '{Path(c).as_posix()}'" for c in clips),
        encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
          "-i", str(list_file), "-c", "copy", str(out_path)])
    return str(out_path)
