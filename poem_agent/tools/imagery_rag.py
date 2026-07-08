# -*- coding: utf-8 -*-
"""
imagery_rag.py —— 意象词典检索(RAG-lite,手册 M2)

MVP 用"LLM 提取意象词 + 词典别名匹配"而不是向量检索,原因:
1. 意象词是封闭集合的专有名词,精确匹配召回率已经很高
2. 教学上先讲清"检索→注入"这个环节的价值,向量化是 v2 的升级项
   (你手搓时可以对照:换成 embedding 检索后,含典故句的命中率提升多少)

两路召回(手册面试题"多路召回"的最小演示):
  - lookup(words):  按 LLM 提取的意象词匹配(语义路)
  - scan_line(line): 直接扫描原句子串(字面路,兜底 LLM 漏提)
"""

import json
from pathlib import Path

import config

_DICT_PATH = config.DATA_DIR / "imagery_dict.json"
_entries: list[dict] = []
_alias_index: dict[str, dict] = {}   # 别名/正名 → 词条


def _load():
    global _entries
    if _entries:
        return
    data = json.loads(_DICT_PATH.read_text(encoding="utf-8"))
    _entries = data["entries"]
    for e in _entries:
        _alias_index[e["name"]] = e
        for a in e.get("aliases", []):
            _alias_index[a] = e


def lookup(words: list[str]) -> list[dict]:
    """
    按意象词列表查词典。
    ≥2 字的词:和别名双向包含即命中(如'明月光'命中'明月');
    单字词:只允许精确等于别名——否则'头'会经'白头''浔阳江头'误命中
    '白发''琵琶'(真实翻车案例,见 run_report 静夜思第 4 句)。
    """
    _load()
    hits, seen = [], set()
    for w in words:
        w = w.strip()
        if not w:
            continue
        for alias, entry in _alias_index.items():
            matched = (w == alias) if len(w) < 2 else (alias in w or w in alias)
            if matched and entry["name"] not in seen:
                seen.add(entry["name"])
                hits.append(entry)
    return hits


def scan_line(line: str) -> list[dict]:
    """字面兜底:直接在原句里找别名子串(别名≥2字才扫,避免'月''风'单字误伤过多)。"""
    _load()
    hits, seen = [], set()
    for alias, entry in _alias_index.items():
        if len(alias) >= 2 and alias in line and entry["name"] not in seen:
            seen.add(entry["name"])
            hits.append(entry)
    return hits


def retrieve(line: str, words: list[str]) -> list[dict]:
    """两路合并去重,最多取 4 条(prompt 里塞太多反而稀释重点)。"""
    merged, seen = [], set()
    for e in lookup(words) + scan_line(line):
        if e["name"] not in seen:
            seen.add(e["name"])
            merged.append(e)
    return merged[:4]
