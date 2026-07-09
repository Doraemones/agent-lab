# -*- coding: utf-8 -*-
"""
01_chat.py —— 命令行聊天机器人（llm-universe C2 Day 1 练习）

用的是 DeepSeek 的 OpenAI 兼容接口，所以照样用 openai 这个 SDK，
只是把 base_url、key、模型名换成 DeepSeek 的。

运行前：把 key 写进同目录上一层的 .env 文件里：
    DEEPSEEK_API_KEY=sk-你的key
然后：
    python 01_chat.py

命令：
    /clear  清空对话历史（但保留 system 人设）
    /exit   退出
"""

import os
import sys
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

# 自动往上找 .env 并把里面的 KEY=值 加载进环境变量
# （llm-universe 就是用这个套路管 API key，比每次 $env: 省事）
load_dotenv(find_dotenv())

# --- Windows 中文终端防乱码：强制 stdout 用 utf-8 ---
# （你之前踩过 conda run 的 gbk 编码坑，这行能省心）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ============ 1. 建客户端 ============
# base_url 指向 DeepSeek 的接口，它兼容 OpenAI 协议，所以能直接用 openai SDK
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

MODEL = "deepseek-chat"  # 通用对话模型(V3)；想要"会推理"的换成 "deepseek-reasoner"(R1)

# ============ 2. system prompt：给机器人设定人设/规则 ============
# system 这条消息只在开头放一次，它是"最高指令"，规定了助手的身份和说话风格。
SYSTEM_PROMPT = "你是一个友好、简洁的中文助手，回答尽量口语化，别啰嗦。"


def new_history():
    """返回一段全新的对话历史，只含 system 那条。"""
    return [{"role": "system", "content": SYSTEM_PROMPT}]


# ============ 3. messages 列表：多轮对话的"记忆"就靠它 ============
# 关键理解：模型本身是"无记忆"的，每次请求你都要把【整段历史】重新发给它。
# 所谓"上下文不丢"，就是这个 list 一直在往后 append，从不丢弃。
messages = new_history()

print("聊天机器人已启动（/clear 清空，/exit 退出）")
print("-" * 40)

# ============ 4. while 主循环 ============
while True:
    user_input = input("你: ").strip()

    # --- 处理命令 ---
    if user_input == "/exit":
        print("再见 👋")
        break
    if user_input == "/clear":
        messages = new_history()
        print("[已清空对话历史]")
        continue
    if not user_input:          # 空输入就跳过，别浪费一次请求
        continue

    # --- 把用户这句话加进历史（role = user）---
    messages.append({"role": "user", "content": user_input})

    # --- 调 API：把【整段 messages】发过去 ---
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,       # 注意：发的是整个列表，不是单句
            temperature=0.7,         # 0=最稳定，越大越发散，见下面讲解
            max_tokens=1024,         # 单次回复最多生成多少 token
            stream=True,
            stream_options={"include_usage": True},
        )
    except Exception as e:
        print(f"[请求出错] {e}")
        messages.pop()               # 出错就把刚加的 user 那条撤回，保持历史干净
        continue

    # --- 流式接收：一边收 chunk 一边逐字打印（这才是 stream=True 的意义）---
    content = ""
    usage = None
    print("助手: ", end="", flush=True)
    for chunk in resp:
        # usage 只在最后一个 chunk 出现（此时 choices 通常为空）——
        # 所以必须在下面 continue 之前先接住它，否则会被一起跳过丢掉。
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        piece = chunk.choices[0].delta.content
        if piece:                       # delta.content 可能是 None（比如首个只带 role 的 chunk）
            print(piece, end="", flush=True)
            content += piece
    print()                             # 收完补个换行
    

    # --- 打印本轮 token 消耗 ---
    if usage:
        print(f"[token] 输入 {usage.prompt_tokens} + 输出 {usage.completion_tokens} = 合计 {usage.total_tokens}")

    # --- 关键一步：把助手的回答也 append 回历史（role = assistant）---
    # 不加这步，下一轮模型就"忘了"自己说过啥，多轮对话会断。
    messages.append({"role": "assistant", "content": content})
