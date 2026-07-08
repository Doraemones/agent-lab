# -*- coding: utf-8 -*-
"""
main.py —— CLI 入口

用法(在 poem-agent 环境下):
    conda activate poem-agent
    python main.py "床前明月光,疑是地上霜。举头望明月,低头思故乡。" --title 静夜思 --author 李白

参数:
    --budget 2.0   单条视频预算(元),超了自动降级
    --fresh        不续传,强制从头跑(默认:上次没跑完会自动从断点继续)

断点续传(手册 M1 验收点):
    每个节点跑完都会把 State 存进 output/checkpoints.sqlite;
    中途 Ctrl+C / 断网 / 崩溃后,原命令重跑即从断掉的那句继续,已花的钱不白花。
"""

import argparse
import hashlib
import sqlite3
import sys
import time
from pathlib import Path

# Windows 中文终端防乱码(你在 01_chat.py 踩过的坑,这里同样处理)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langgraph.checkpoint.sqlite import SqliteSaver

import config
from graph import build_graph


def _safe_name(s: str) -> str:
    """目录名只保留中日韩文字和字母数字"""
    return "".join(c for c in s if c.isalnum())[:20] or "poem"


def main():
    ap = argparse.ArgumentParser(description="古诗词视频生成 Agent(参考实现)")
    ap.add_argument("poem", help="整首绝句,含标点")
    ap.add_argument("--title", default="", help="诗名(不给则让模型判断)")
    ap.add_argument("--author", default="", help="作者(不给则让模型判断)")
    ap.add_argument("--budget", type=float, default=config.BUDGET_PER_VIDEO,
                    help=f"单条预算(元),默认 {config.BUDGET_PER_VIDEO}")
    ap.add_argument("--fresh", action="store_true", help="忽略断点,从头重跑")
    args = ap.parse_args()

    config.OUTPUT_DIR.mkdir(exist_ok=True)

    # thread_id 由诗文内容决定 → 同一首诗天然对应同一条断点记录
    base_tid = hashlib.md5(args.poem.encode("utf-8")).hexdigest()[:10]
    workdir = config.OUTPUT_DIR / f"{_safe_name(args.title or args.poem)}_{base_tid[:6]}"
    workdir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(config.CHECKPOINT_DB, check_same_thread=False)
    app = build_graph(SqliteSaver(conn))

    cfg = {"configurable": {"thread_id": base_tid}}
    snap = app.get_state(cfg)
    resumable = bool(snap.values) and bool(snap.next) and not args.fresh

    mode = "真实生图 + VLM 质检" if config.has_t2i() else "⚠ 降级模式(未配 SILICONFLOW_API_KEY,画面=水墨字卡)"
    print("=" * 56)
    print(f"古诗词视频 Agent | 模式:{mode}")
    print("=" * 56, flush=True)

    if resumable:
        print(f"发现断点(下一步:{snap.next[0]}),继续上次的活……\n")
        final = app.invoke(None, cfg)          # 传 None = 从 checkpoint 恢复
    else:
        if snap.values and not args.fresh:
            # 上次已跑完:换一个新 thread 重新生成,老记录留档
            cfg = {"configurable": {"thread_id": f"{base_tid}-{int(time.time())}"}}
        final = app.invoke({
            "poem": args.poem, "title": args.title, "author": args.author,
            "budget": args.budget, "workdir": str(workdir),
            "line_index": 0, "line_results": [], "total_cost": 0.0,
            "force_fallback": False, "started_at": time.time(),
        }, cfg)

    print("\n" + "=" * 56)
    print(f"完成!成片:{final['final_video']}")
    print(f"报告:{final['report_path']}")
    print(f"总成本:{final['total_cost']:.4f} 元")
    print("=" * 56)


if __name__ == "__main__":
    main()
