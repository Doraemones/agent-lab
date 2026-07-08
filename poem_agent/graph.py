# -*- coding: utf-8 -*-
"""
graph.py —— LangGraph 编排:主图 + 单句子图

================ 主图(游标循环) ================
START → parse_poem → plan_routes ─┬─(还有句子)→ process_line ─┐
                                  │       ↑___________________│
                                  └─(处理完)→ gen_audio → compose_clips
                                              → concat_video → report → END

================ 单句子图(质检反思环 ⭐) ================
enrich_imagery → gen_shot_prompt → gen_image ─┬─(有图)→ qc_image ─┬─(通过)→ END
                                              │                   ├─(不过,还有次数)→ rewrite_prompt → gen_image
                                              └─(没图/无key)→ fallback ←─(不过,次数用尽)┘
                                                                → END

"哪个箭头是 agent 在做决策?"(手册过关问题)——
  两条条件边:qc_image 之后的三岔口(模型质检结果决定走向),
  以及 plan_routes 里每句 standard/premium 的判定(模型按诗意决定花钱策略)。
  其余都是固定流程。这就是"agent 决策点"和"固定管线"的边界。
"""

import time
from pathlib import Path
from typing import TypedDict, Literal

from langgraph.graph import StateGraph, START, END

import config
import llm
from state import PoemState, LineResult, QCRecord
from tools import imagery_rag, t2i, vlm_qc, tts, video, fallback


def _log(msg: str, indent: int = 0):
    print("    " * indent + msg, flush=True)


# ═══════════════════════════ 单句子图 ═══════════════════════════

class LineWork(TypedDict, total=False):
    """单句子图的工作 State(比主图细,只活在一句诗的生命周期里)"""
    index: int
    line: str
    route: str                # standard / premium
    style_anchor: str
    theme: str
    line_emotion: str
    workdir: str
    imagery_notes: list[dict]
    must_have: list[str]
    scene: str                # LLM 输出的纯画面描述(不含风格锚定)
    shot_prompt: str          # style_anchor + scene = 最终生图 prompt
    prompt_history: list[str]
    candidates: list[str]     # 本轮生成的候选图(premium 一次 2 张)
    image_path: str
    qc_attempts: int
    qc_history: list[QCRecord]
    last_passed: bool
    degraded: bool
    cost: float


def enrich_imagery(ws: LineWork) -> dict:
    """M2:LLM 提意象词 → 词典检索 → 命中条目(视觉要点+易错)注入后续分镜"""
    data, c = llm.chat_json(
        "你是古典诗词专家。",
        f"从这句诗中提取意象名词(2-5个,只要具体物象):「{ws['line']}」\n"
        '输出 {"imagery_words": ["...", "..."]}',
    )
    words = [str(w) for w in data.get("imagery_words", [])]
    notes = imagery_rag.retrieve(ws["line"], words)
    _log(f"意象检索:提取 {words} → 词典命中 {[n['name'] for n in notes] or '无'}", 2)
    return {"imagery_notes": notes, "cost": ws.get("cost", 0.0) + c}


def gen_shot_prompt(ws: LineWork) -> dict:
    """分镜:诗句 + 意象要点(RAG 注入)→ 画面描述 + 必现意象清单(质检的核对依据)"""
    brief = "\n".join(
        f"- {n['name']}:视觉要点:{n['visual']};易错:{n['pitfalls']}"
        for n in ws.get("imagery_notes", [])
    ) or "(无词典命中,凭诗句直译画面)"
    data, c = llm.chat_json(
        "你是古诗配画的分镜师,把诗句转成文生图的画面描述。",
        f"诗句:「{ws['line']}」\n全诗主题:{ws['theme']}\n本句情感:{ws['line_emotion']}\n"
        f"意象参考(务必遵守视觉要点、避开易错点):\n{brief}\n\n"
        "输出 JSON:\n"
        '{"scene": "60~100字纯画面描述:主体/构图/光线/色调,不要出现\'诗\'字样,'
        '不要任何现代元素", "must_have": ["3-5个画面中必须出现的具体可见意象"]}',
    )
    scene = str(data.get("scene", ws["line"]))
    shot = f"{ws['style_anchor']}。{scene}"     # ⭐ 锚定前缀由代码拼接,保证四句风格一致
    _log(f"分镜 prompt:{scene[:40]}… | 必现意象:{data.get('must_have')}", 2)
    return {
        "scene": scene, "shot_prompt": shot,
        "must_have": [str(m) for m in data.get("must_have", [])][:5],
        "prompt_history": ws.get("prompt_history", []) + [shot],
        "cost": ws.get("cost", 0.0) + c,
    }


def gen_image(ws: LineWork) -> dict:
    """生图:standard 1 张;premium(名场面句)生 2 张候选让 VLM 选优(成本路由的落点)"""
    attempt = ws.get("qc_attempts", 0) + 1
    n = config.PREMIUM_CANDIDATES if ws["route"] == "premium" else 1
    candidates, cost = [], ws.get("cost", 0.0)
    for k in range(n):
        p = Path(ws["workdir"]) / f"line{ws['index']}_try{attempt}_{k}.png"
        path, c = t2i.generate(ws["shot_prompt"], p)
        cost += c
        if path:
            candidates.append(path)
    _log(f"生图(第 {attempt} 次):请求 {n} 张,成功 {len(candidates)} 张", 2)
    return {"candidates": candidates, "cost": cost}


def after_gen_image(ws: LineWork) -> str:
    """条件边:没图(无 key 或 API 连败)→ 直接降级,别让质检节点空转"""
    return "qc" if ws.get("candidates") else "fallback"


def qc_image(ws: LineWork) -> dict:
    """M3:VLM 逐张审图;premium 多候选时选最优(passed 优先→氛围分→缺失少)"""
    attempt = ws.get("qc_attempts", 0) + 1
    scored: list[tuple[str, QCRecord]] = []
    cost = ws.get("cost", 0.0)
    for path in ws["candidates"]:
        rec, c = vlm_qc.qc(path, ws["line"], ws["must_have"], attempt)
        cost += c
        scored.append((path, rec))
    best_path, best = max(
        scored, key=lambda pr: (pr[1]["passed"], pr[1]["mood_score"], -len(pr[1]["missing"])))
    # 落选记录在前、当选记录在最后 → 改写节点直接读 qc_history[-1]
    history = ws.get("qc_history", []) + [r for p, r in scored if p != best_path] + [best]
    tag = "✓ 通过" if best["passed"] else f"✗ 不过(缺:{best['missing']} 氛围:{best['mood_score']})"
    _log(f"质检(第 {attempt} 次):{tag}" + (" [模拟]" if best["simulated"] else ""), 2)
    return {"image_path": best_path, "qc_attempts": attempt,
            "qc_history": history, "last_passed": best["passed"], "cost": cost}


def decide_after_qc(ws: LineWork) -> str:
    """⭐ 反思环的三岔口:通过 / 改写重试 / 认输降级(手册 M3 的灵魂)"""
    if ws["last_passed"]:
        return "pass"
    if ws["qc_attempts"] <= config.MAX_QC_RETRY:   # 第 1、2 次失败还有机会
        return "rewrite"
    return "fallback"                               # 重试额度用尽


def rewrite_prompt(ws: LineWork) -> dict:
    """把 VLM 的问题描述"喂回"prompt——反思环的闭环所在(面试第 17 问)"""
    last = ws["qc_history"][-1]
    data, c = llm.chat_json(
        "你是文生图提示词医生:根据质检意见修复画面描述。",
        f"诗句:「{ws['line']}」\n原画面描述:{ws['scene']}\n"
        f"质检结论:缺失意象 {last['missing']};问题:{last['problems']}\n\n"
        "改写画面描述:缺失的意象放到句首显式强调,对质检点名的问题加明确的否定"
        "(如'画面中不得出现现代家具');保持原意境不跑偏。\n"
        '输出 {"scene": "改写后的60~100字画面描述"}',
    )
    scene = str(data.get("scene", ws["scene"]))
    shot = f"{ws['style_anchor']}。{scene}"
    _log(f"改写 prompt:针对 {last['missing'] or last['problems'][:20]} 重写", 2)
    return {"scene": scene, "shot_prompt": shot,
            "prompt_history": ws["prompt_history"] + [shot],
            "cost": ws.get("cost", 0.0) + c}


def line_fallback(ws: LineWork) -> dict:
    """降级:水墨字卡。agent 的"优雅失败"——交付一个可用的兜底,而不是报错终止"""
    card = fallback.make_ink_card(
        ws["line"], Path(ws["workdir"]) / f"line{ws['index']}_card.png")
    _log("降级:水墨字卡兜底", 2)
    return {"image_path": card, "degraded": True}


def build_line_graph():
    g = StateGraph(LineWork)
    g.add_node("enrich_imagery", enrich_imagery)
    g.add_node("gen_shot_prompt", gen_shot_prompt)
    g.add_node("gen_image", gen_image)
    g.add_node("qc_image", qc_image)
    g.add_node("rewrite_prompt", rewrite_prompt)
    g.add_node("fallback", line_fallback)

    g.add_edge(START, "enrich_imagery")
    g.add_edge("enrich_imagery", "gen_shot_prompt")
    g.add_edge("gen_shot_prompt", "gen_image")
    g.add_conditional_edges("gen_image", after_gen_image,
                            {"qc": "qc_image", "fallback": "fallback"})
    g.add_conditional_edges("qc_image", decide_after_qc,
                            {"pass": END, "rewrite": "rewrite_prompt", "fallback": "fallback"})
    g.add_edge("rewrite_prompt", "gen_image")
    g.add_edge("fallback", END)
    return g.compile()


_line_app = build_line_graph()


# ═══════════════════════════ 主图 ═══════════════════════════

def parse_poem(state: PoemState) -> dict:
    """解析:拆句 + 主题情感 + ⭐风格锚定(全诗统一画风的关键)+ 每句运镜"""
    _log("【解析诗歌】")
    data, c = llm.chat_json(
        "你是古典诗词专家。",
        f"解析这首诗:\n{state['poem']}\n\n输出 JSON:\n"
        "{\n"
        '  "title": "诗名(不知道就起一个贴切的)", "author": "作者(不知道写佚名)",\n'
        '  "lines": ["逐句拆分,每句不带标点"],\n'
        '  "theme": "全诗主题一句话", "emotion": "整体情感基调",\n'
        '  "style_anchor": "40-70字统一画面风格描述:绘画风格/色调/年代场景/构图气质,'
        '将作为每句配图的公共前缀",\n'
        '  "per_line": [{"line_emotion": "该句情感", "camera": "in|out|pan"}]\n'
        "}\n"
        "camera 选择依据:凝视/思念选 in(推近),收束/释然选 out(拉远),写景/叙事选 pan(平移)。",
    )
    lines = [str(x) for x in data.get("lines", [])]
    if not 2 <= len(lines) <= 8:
        raise ValueError(f"拆句结果异常({len(lines)} 句)。MVP 只支持绝句/律诗,请检查输入:{lines}")
    per = data.get("per_line", [])
    cameras = [(p.get("camera") if p.get("camera") in ("in", "out", "pan") else "in")
               for p in per] + ["in"] * len(lines)
    emotions = [str(p.get("line_emotion", "")) for p in per] + [""] * len(lines)
    title = state.get("title") or str(data.get("title", "无题"))     # CLI 传的优先
    author = state.get("author") or str(data.get("author", "佚名"))
    _log(f"《{title}》{author} | {len(lines)} 句 | 主题:{data.get('theme')}")
    _log(f"风格锚定:{data.get('style_anchor')}", 1)
    return {
        "lines": lines, "title": title, "author": author,
        "theme": str(data.get("theme", "")), "emotion": str(data.get("emotion", "")),
        "style_anchor": str(data.get("style_anchor", "中国水墨画风格,古典意境,大量留白")),
        "cameras": cameras[: len(lines)], "line_emotions": emotions[: len(lines)],
        "total_cost": state.get("total_cost", 0.0) + c,
    }


def plan_routes(state: PoemState) -> dict:
    """M4 成本路由:模型判定哪 1-2 句是"名场面"值得加钱(premium=多候选图选优)"""
    _log("【成本路由】")
    numbered = "\n".join(f"{i}. {l}" for i, l in enumerate(state["lines"]))
    data, c = llm.chat_json(
        "你是短视频导演,要在预算内分配镜头成本。",
        f"全诗主题:{state['theme']}\n诗句:\n{numbered}\n\n"
        "最多选 1-2 句「名场面」(画面冲击力最强/情感最高潮)给 premium 待遇"
        "(多张候选图选优),其余 standard(单图)。\n"
        '输出 {"routes": [{"route": "standard|premium", "reason": "一句话理由"}, ...],'
        "数组长度=诗句数,顺序对应}",
    )
    items = data.get("routes", [])
    routes, reasons, premium_used = [], [], 0
    for i in range(len(state["lines"])):
        it = items[i] if i < len(items) else {}
        r = it.get("route", "standard")
        if r == "premium" and premium_used >= 2:     # 硬约束:模型想多花钱也不行
            r = "standard"
        premium_used += r == "premium"
        routes.append(r)
        reasons.append(str(it.get("reason", "")))
        _log(f"第 {i+1} 句 [{r:8s}] {reasons[-1]}", 1)
    return {"routes": routes, "route_reasons": reasons,
            "total_cost": state["total_cost"] + c}


def next_step(state: PoemState) -> str:
    """游标条件边:还有句子没处理就继续循环,否则进入音视频收尾"""
    return "process_line" if state["line_index"] < len(state["lines"]) else "gen_audio"


def process_line(state: PoemState) -> dict:
    """主图游标节点:调用单句子图;预算超了强制降级(M4 的预算保险丝)"""
    i = state["line_index"]
    line = state["lines"][i]
    _log(f"【第 {i+1}/{len(state['lines'])} 句】{line}")

    force = state.get("force_fallback", False)
    if not force and state["total_cost"] >= state["budget"]:
        _log(f"⚠ 成本 {state['total_cost']:.3f} 元已超预算 {state['budget']} 元,"
             f"本句起强制降级", 1)
        force = True

    if force:
        card = fallback.make_ink_card(line, Path(state["workdir"]) / f"line{i}_card.png")
        result = LineResult(
            index=i, line=line, route="forced_fallback", route_reason="超预算强制降级",
            imagery_notes=[], must_have=[], shot_prompt="", prompt_history=[],
            image_path=card, qc_attempts=0, qc_history=[], degraded=True,
            camera=state["cameras"][i], cost=0.0)
        line_cost = 0.0
    else:
        work = _line_app.invoke(LineWork(
            index=i, line=line, route=state["routes"][i],
            style_anchor=state["style_anchor"], theme=state["theme"],
            line_emotion=state["line_emotions"][i], workdir=state["workdir"],
            cost=0.0, qc_attempts=0, qc_history=[], prompt_history=[], degraded=False,
        ))
        line_cost = work.get("cost", 0.0)
        result = LineResult(
            index=i, line=line, route=state["routes"][i],
            route_reason=state["route_reasons"][i],
            imagery_notes=work.get("imagery_notes", []),
            must_have=work.get("must_have", []),
            shot_prompt=work.get("shot_prompt", ""),
            prompt_history=work.get("prompt_history", []),
            image_path=work["image_path"], qc_attempts=work.get("qc_attempts", 0),
            qc_history=work.get("qc_history", []), degraded=work.get("degraded", False),
            camera=state["cameras"][i], cost=line_cost)

    return {"line_results": state.get("line_results", []) + [result],
            "line_index": i + 1, "force_fallback": force,
            "total_cost": state["total_cost"] + line_cost}


def gen_audio(state: PoemState) -> dict:
    """edge-tts 逐句吟诵(免费);句尾补句号让停顿更自然"""
    _log("【TTS 吟诵】")
    paths, durs = [], []
    for i, line in enumerate(state["lines"]):
        p, d = tts.synth(line + "。", Path(state["workdir"]) / f"audio_{i}.mp3")
        paths.append(p)
        durs.append(d)
        _log(f"第 {i+1} 句:{d:.2f}s", 1)
    return {"audio_paths": paths, "audio_durations": durs}


def compose_clips(state: PoemState) -> dict:
    """每句合成 5 秒左右的带字幕运镜片段(时长跟着吟诵音频走)"""
    _log("【合成片段】")
    clips = []
    for i, line in enumerate(state["lines"]):
        r = state["line_results"][i]
        dur = state["audio_durations"][i] + config.LINE_PAD_SEC
        clip = video.make_clip(
            r["image_path"], state["audio_paths"][i], line,
            Path(state["workdir"]) / f"clip_{i}.mp4", dur, r["camera"])
        clips.append(clip)
        _log(f"clip_{i}.mp4({dur:.1f}s,运镜 {r['camera']})", 1)
    return {"clip_paths": clips}


def concat_video(state: PoemState) -> dict:
    """片头字卡 + 逐句片段 → 成片"""
    _log("【总装拼片】")
    wd = Path(state["workdir"])
    title_img = fallback.make_ink_card(state["title"], wd / "title.png",
                                       sub_text=state["author"])
    title_clip = video.make_silent_clip(title_img, wd / "clip_title.mp4",
                                        config.TITLE_CARD_SEC)
    final = video.concat([title_clip] + state["clip_paths"], wd / "final.mp4")
    _log(f"成片:{final}")
    return {"final_video": final}


def report(state: PoemState) -> dict:
    """评估报告(M6 指标的雏形):一次通过率/平均重试/成本/耗时,全部真实数据"""
    results = state["line_results"]
    real = [r for r in results if r["route"] != "forced_fallback"]
    simulated = any(rec["simulated"] for r in results for rec in r["qc_history"])
    first_pass = sum(1 for r in real if r["qc_attempts"] == 1 and not r["degraded"])
    retries = [max(r["qc_attempts"] - 1, 0) for r in real]
    elapsed = time.time() - state["started_at"]

    md = [f"# 运行报告:《{state['title']}》{state['author']}", ""]
    md.append(f"- 模式:{'⚠ 降级模式(无 SILICONFLOW_API_KEY,质检为模拟)' if simulated or not config.has_t2i() else '真实生图 + VLM 质检'}")
    md.append(f"- 一次通过率:{first_pass}/{len(real) or 1}"
              f"({first_pass / (len(real) or 1) * 100:.0f}%)")
    md.append(f"- 平均重试:{(sum(retries) / len(retries)) if retries else 0:.2f} 次/句")
    md.append(f"- 降级句数:{sum(1 for r in results if r['degraded'])}/{len(results)}")
    md.append(f"- 总成本:{state['total_cost']:.4f} 元(预算 {state['budget']} 元)")
    md.append(f"- 总耗时:{elapsed:.0f} 秒")
    md.append(f"- 成片:{state['final_video']}\n")
    md.append("| # | 诗句 | 路由 | 重试 | 结局 | 成本(元) |")
    md.append("|---|------|------|------|------|----------|")
    for r in results:
        ending = "降级字卡" if r["degraded"] else "生图通过"
        md.append(f"| {r['index']+1} | {r['line']} | {r['route']} "
                  f"| {max(r['qc_attempts']-1, 0)} | {ending} | {r['cost']:.4f} |")
    md.append("\n## 质检明细(反思环留档,面试演示素材)\n")
    for r in results:
        md.append(f"### 第 {r['index']+1} 句:{r['line']}")
        md.append(f"- 路由:{r['route']}({r['route_reason']})")
        md.append(f"- 必现意象:{r['must_have']}")
        for rec in r["qc_history"]:
            flag = "✓" if rec["passed"] else "✗"
            md.append(f"- 第 {rec['attempt']} 次 {flag} 氛围 {rec['mood_score']}/5,"
                      f"缺失 {rec['missing']},问题:{rec['problems']}")
        if len(r["prompt_history"]) > 1:
            md.append(f"- prompt 共改写 {len(r['prompt_history'])-1} 次(全文见 json)")
        md.append("")

    wd = Path(state["workdir"])
    report_path = wd / "run_report.md"
    report_path.write_text("\n".join(md), encoding="utf-8")
    import json as _json
    (wd / "run_report.json").write_text(
        _json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"【报告】{report_path}")
    return {"report_path": str(report_path)}


def build_graph(checkpointer=None):
    g = StateGraph(PoemState)
    g.add_node("parse_poem", parse_poem)
    g.add_node("plan_routes", plan_routes)
    g.add_node("process_line", process_line)
    g.add_node("gen_audio", gen_audio)
    g.add_node("compose_clips", compose_clips)
    g.add_node("concat_video", concat_video)
    g.add_node("report", report)

    g.add_edge(START, "parse_poem")
    g.add_edge("parse_poem", "plan_routes")
    # 两条同款条件边组成"游标循环":这是 checkpoint 能按句粒度续传的原因
    g.add_conditional_edges("plan_routes", next_step,
                            {"process_line": "process_line", "gen_audio": "gen_audio"})
    g.add_conditional_edges("process_line", next_step,
                            {"process_line": "process_line", "gen_audio": "gen_audio"})
    g.add_edge("gen_audio", "compose_clips")
    g.add_edge("compose_clips", "concat_video")
    g.add_edge("concat_video", "report")
    g.add_edge("report", END)
    return g.compile(checkpointer=checkpointer)
