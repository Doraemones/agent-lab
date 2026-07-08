# -*- coding: utf-8 -*-
"""
state.py —— State 先行!(手册 Day 19-21 的核心要求)

整个 agent 的"记忆"和"决策依据"全在这两个结构里。
手册验收点逐条对应:
  - 诗句列表        → PoemState.lines
  - 各句素材路径    → LineResult.image_path / PoemState.audio_paths / clip_paths
  - 重试计数        → LineResult.qc_attempts
  - 成本累计        → LineResult.cost / PoemState.total_cost

为什么用 TypedDict 而不是 pydantic:LangGraph 的 State 就是 dict 合并语义,
节点返回"部分更新",TypedDict 足够、直观、无魔法——教学参考选透明的。
"""

from typing import TypedDict, Literal


class QCRecord(TypedDict):
    """一次 VLM 质检的完整记录(留档,面试演示'错图→改写→通过'就靠它)"""
    attempt: int              # 第几次尝试(1 起)
    passed: bool
    present: list[str]        # 画面里核对到的意象
    missing: list[str]        # 缺失的必现意象(判不合格的硬依据)
    mood_score: int           # 氛围匹配 1-5(软判据)
    problems: str             # VLM 描述的具体问题 → 会反馈进改写 prompt
    simulated: bool           # True = 无 key 模拟结果(降级模式,不算真质检)


class LineResult(TypedDict):
    """单句诗的全部处理结果(单句子图的输出)"""
    index: int
    line: str
    route: Literal["standard", "premium", "forced_fallback"]
    # standard = 单图+运镜 | premium = 名场面:多候选图选优 | forced_fallback = 超预算强制降级
    route_reason: str         # 路由节点为什么这么判(面试:"每句走了哪条路、为什么")
    imagery_notes: list[dict] # 意象词典命中的条目(RAG 注入的证据)
    must_have: list[str]      # 生图 prompt 里承诺"必须出现"的意象 → 质检逐项核对
    shot_prompt: str          # 最终采用的分镜 prompt
    prompt_history: list[str] # 每次改写的 prompt 留档(演示反思环)
    image_path: str
    qc_attempts: int          # 重试计数(手册点名要的字段)
    qc_history: list[QCRecord]
    degraded: bool            # True = 最终走了水墨字卡降级
    camera: Literal["in", "out", "pan"]  # 运镜:推近/拉远/平移(按句子情感选)
    cost: float               # 这一句花了多少钱


class PoemState(TypedDict, total=False):
    """主图 State。total=False:各节点只填自己那部分,LangGraph 负责合并。"""
    # ---- 输入 ----
    poem: str
    title: str
    author: str
    budget: float
    workdir: str              # output/<诗名>/ 本次运行的产物目录
    # ---- parse_poem 产出 ----
    lines: list[str]
    theme: str                # 全诗主题(一句话)
    emotion: str              # 整体情感基调
    style_anchor: str         # ⭐ 风格锚定前缀:所有分镜 prompt 共享,保证 4 句画面风格一致
                              #   (面试第 18 问"多句一致性怎么保证"的 MVP 答案)
    line_emotions: list[str]  # 每句的情感注解(给分镜和运镜选择用)
    cameras: list[str]        # 每句运镜:in 缓推 / out 缓拉 / pan 平移
    # ---- plan_routes 产出 ----
    routes: list[str]         # 每句 standard/premium
    route_reasons: list[str]
    # ---- 游标循环 ----
    line_index: int           # 当前处理到第几句(条件边靠它决定继续循环还是收尾)
    line_results: list[LineResult]
    force_fallback: bool      # 超预算后置 True,后续句子直接降级(手册 M4 预算控制)
    # ---- 音视频合成 ----
    audio_paths: list[str]
    audio_durations: list[float]
    clip_paths: list[str]
    final_video: str
    # ---- 统计 ----
    total_cost: float
    started_at: float         # time.time(),报告里算总耗时
    report_path: str
