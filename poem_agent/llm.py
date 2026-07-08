# -*- coding: utf-8 -*-
"""
llm.py —— DeepSeek 封装:普通对话 + JSON 结构化输出 + 按 token 计费

刻意不套 langchain 的 LLM 包装,直接用 openai SDK(你在 01_chat.py 已经会了)。
教学点:
1. agent 里 LLM 的输出要进程序逻辑,所以必须"结构化"——JSON mode + 兜底解析
2. 每次调用都算钱,返回 (结果, cost),由调用方累计进 State(手册的成本意识)
"""

import json
import re

from openai import OpenAI

import config

_client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)


def _cost_of(usage) -> float:
    """按 token 用量算这次调用花的钱(元)"""
    if usage is None:
        return 0.0
    return (
        usage.prompt_tokens / 1_000_000 * config.PRICE["llm_in_per_1m"]
        + usage.completion_tokens / 1_000_000 * config.PRICE["llm_out_per_1m"]
    )


def chat(system: str, user: str, temperature: float = 0.7) -> tuple[str, float]:
    """普通文本输出。返回 (文本, 花费)。"""
    resp = _client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content, _cost_of(resp.usage)


def chat_json(system: str, user: str, temperature: float = 0.3) -> tuple[dict, float]:
    """
    结构化输出:要求模型返回 JSON,并做两层兜底。
    - 第一层:response_format=json_object(DeepSeek 支持 OpenAI 的 JSON mode)
    - 第二层:万一还夹了代码围栏/废话,正则抠出最外层 {...} 再 parse
    temperature 默认 0.3:结构化任务要稳定(Day 1 你总结过 temperature 的取舍)
    """
    resp = _client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system + "\n\n只输出一个合法 JSON 对象,不要任何其他文字。"},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content
    cost = _cost_of(resp.usage)
    try:
        return json.loads(text), cost
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)   # 兜底:抠最外层大括号
        if m:
            return json.loads(m.group()), cost
        raise ValueError(f"LLM 没有返回合法 JSON:{text[:200]}")
