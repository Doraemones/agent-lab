# -*- coding: utf-8 -*-
"""
fallback.py —— 降级方案:PIL 生成"水墨底图 + 书法字卡"(手册 M3 的兜底路径)

三个用途:
1. 质检两次仍不合格 → 该句降级为字卡(agent 的优雅失败,面试考点)
2. 无 SILICONFLOW_API_KEY 的降级模式 → 所有句子都用它,保证链路能跑通
3. 片头标题字卡

设计:宣纸底色 + 随机纹理斑驳 + 角落淡墨晕染 + 竖排楷体 + 朱红印章。
全程 PIL,零成本零网络。
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

_PUNCT = "，。！？、；：·,.!?;: "


def _strip_punct(s: str) -> str:
    return "".join(c for c in s if c not in _PUNCT)


def _paper_base(w: int, h: int, seed: int) -> Image.Image:
    """宣纸底:米色 + 低透明度斑驳纹理 + 角落墨晕"""
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (243, 236, 221))          # 宣纸米色

    # 斑驳纹理:一层随机浅灰椭圆,重度模糊后叠加,模拟纸纹
    mottle = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mottle)
    for _ in range(70):
        x, y = rnd.randint(-100, w), rnd.randint(-100, h)
        r = rnd.randint(40, 220)
        md.ellipse([x, y, x + r, y + int(r * 0.7)], fill=rnd.randint(6, 16))
    mottle = mottle.filter(ImageFilter.GaussianBlur(50))
    img = Image.composite(Image.new("RGB", (w, h), (215, 205, 185)), img, mottle)

    # 角落淡墨晕染:两三团深灰大圆,大模糊,像洇开的墨
    ink = Image.new("L", (w, h), 0)
    idr = ImageDraw.Draw(ink)
    corners = [(int(w * 0.85), int(h * 0.9)), (int(w * 0.1), int(h * 0.08))]
    for cx, cy in corners:
        for _ in range(3):
            r = rnd.randint(90, 200)
            ox, oy = rnd.randint(-60, 60), rnd.randint(-60, 60)
            idr.ellipse([cx + ox - r, cy + oy - r, cx + ox + r, cy + oy + r],
                        fill=rnd.randint(14, 30))
    ink = ink.filter(ImageFilter.GaussianBlur(70))
    img = Image.composite(Image.new("RGB", (w, h), (70, 72, 75)), img, ink)
    return img


def _draw_vertical(draw: ImageDraw.ImageDraw, chars: str, font: ImageFont.FreeTypeFont,
                   cx: int, cy: int, size: int, fill, jitter: random.Random):
    """竖排一列字,cx 为列中心,cy 为整列顶端;微小抖动模拟手写"""
    step = int(size * 1.18)
    for i, ch in enumerate(chars):
        jx = jitter.randint(-3, 3)
        draw.text((cx - size // 2 + jx, cy + i * step), ch, font=font, fill=fill)


def make_ink_card(text: str, out_path: str | Path, sub_text: str = "",
                  w: int = config.VIDEO_W, h: int = config.VIDEO_H) -> str:
    """
    生成一张竖排书法字卡。
    text     主文字(诗句或标题),竖排居中
    sub_text 副文字(如作者),小字排在主列左下
    """
    text = _strip_punct(text)
    seed = hash(text) & 0xFFFF
    rnd = random.Random(seed)
    img = _paper_base(w, h, seed)
    draw = ImageDraw.Draw(img)

    # 主列:字号随字数自适应(5 字更大,7 字略小),整列垂直居中
    n = max(len(text), 1)
    size = min(int(h * 0.62 / n), int(w * 0.28))
    font = ImageFont.truetype(config.FONT_PATH, size)
    col_h = int(size * 1.18) * n
    cx, cy = w // 2, (h - col_h) // 2
    _draw_vertical(draw, text, font, cx, cy, size, (38, 38, 42), rnd)

    # 副列(作者):小字,主列左侧偏下
    if sub_text:
        sub = _strip_punct(sub_text)
        ssize = max(int(size * 0.32), 40)
        sfont = ImageFont.truetype(config.FONT_PATH, ssize)
        scx = cx - int(size * 0.95)
        scy = cy + col_h - int(ssize * 1.18) * len(sub) - int(size * 0.2)
        _draw_vertical(draw, sub, sfont, scx, scy, ssize, (90, 88, 90), rnd)

    # 朱红印章:主列右下,白字"诗境"
    seal_s = max(int(size * 0.42), 56)
    sx = cx + int(size * 0.72)
    sy = cy + col_h + int(size * 0.15)
    sy = min(sy, h - seal_s * 2 - 40)                    # 别画出画布
    draw.rectangle([sx, sy, sx + seal_s, sy + seal_s * 2], fill=(158, 44, 38))
    seal_font = ImageFont.truetype(config.FONT_PATH, int(seal_s * 0.72))
    for i, ch in enumerate("诗境"):
        draw.text((sx + seal_s * 0.15, sy + 6 + i * seal_s * 0.92), ch,
                  font=seal_font, fill=(240, 232, 220))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return str(out_path)
