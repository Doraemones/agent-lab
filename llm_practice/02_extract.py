# -*- coding: utf-8 -*-
"""
02_extract.py —— JD 结构化抽取（llm-universe C2 Day 3 练习）

做：输入一段招聘 JD 文本，输出严格 JSON：{岗位名, 技能要求[], 薪资, 城市, 学历要求}
    用 json.loads 校验，解析失败自动重试（最多 3 次），结果追加写进 jobs.csv。

关键技术点：
  - response_format={"type":"json_object"} 让模型只吐 JSON（DeepSeek JSON mode）
  - prompt 里必须出现 "json" 字样，且强烈建议给一个 JSON 示例，否则可能吐一堆空白
  - 英文 key 存储，中文表头展示（FIELD_MAP 做映射）
  - JD 是多行的，不能用单个 input()，要按空行分段读
"""
import os
import json
import csv
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ============ 1. system prompt：带 JSON 示例，字段固定 ============
# 注意三件事：①出现了 "JSON" 这个词（json_mode 要求）②给了完整示例（防空白洪水）
#           ③明确说找不到填 null / 空数组，让输出 schema 永远一致
SYSTEM_PROMPT = """你是一个招聘 JD 解析器。用户给你一段招聘 JD 文本，你只输出一个严格合法的 JSON 对象，
不要任何多余文字，不要 markdown 代码块（不要 ```）。

字段固定为这 5 个，找不到的值填 null，skills 找不到填空数组 []：
- title:     岗位名，字符串
- skills:    技能要求，字符串数组
- salary:    薪资，字符串（原文怎么写就怎么填，如 "20k-35k·14薪"）
- city:      城市，字符串
- education: 学历要求，字符串

示例输出：
{
  "title": "后端开发工程师",
  "skills": ["Python", "MySQL", "Redis", "Docker"],
  "salary": "20k-35k·14薪",
  "city": "深圳",
  "education": "本科及以上"
}
"""

# 英文 key → 中文表头 的映射（存储用英文，展示/CSV 用中文）
FIELD_MAP = {
    "title": "岗位名",
    "skills": "技能要求",
    "salary": "薪资",
    "city": "城市",
    "education": "学历要求",
}


# ============ 2. 核心：抽取 + 校验 + 重试 ============
def extract_jd(jd_text, max_retries=3):
    """把一段 JD 文本解析成 dict；json.loads 校验失败就重试，最多 max_retries 次。

    成功 → 返回 dict；3 次都失败 → 返回 None（交给调用方决定跳过还是记录）。
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": jd_text},
    ]

    for attempt in range(1, max_retries + 1):
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,          # 抽取任务：要稳定、可复现，不要发散
        )
        raw = resp.choices[0].message.content

        # ---- 校验这一步：能被 json.loads 解析成对象，才算“合法 JSON” ----
        try:
            return json.loads(raw)          # 成功，直接返回，不再重试
        except json.JSONDecodeError as e:
            print(f"    ⚠ 第 {attempt}/{max_retries} 次 JSON 非法：{e}")
            # 关键：temperature=0 时，原样重发会得到一模一样的坏结果。
            # 所以把“上次的坏输出 + 纠错指令”塞回对话，让模型看着错误去改。
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": "上面的输出不是合法 JSON，请只返回一个合法的 JSON 对象，不要任何多余内容。",
            })

    return None   # 重试用尽仍失败


# ============ 3. 存 CSV（英文 key → 中文表头，skills 列表拼成一串）============
def save_to_csv(rows, path="jobs.csv"):
    headers = list(FIELD_MAP.values())          # 中文表头
    file_exists = os.path.exists(path)
    # utf-8-sig 带 BOM，Excel 双击打开中文不乱码
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:                     # 文件不存在才写表头，避免追加时重复
            writer.writeheader()
        for data in rows:
            row = {}
            for en, zh in FIELD_MAP.items():
                val = data.get(en)              # 用 .get，字段缺了也不报错
                if isinstance(val, list):       # skills 是数组 → 拼成 "Python、MySQL"
                    val = "、".join(val) if val else ""
                row[zh] = "" if val is None else val
            writer.writerow(row)


# ============ 4. 读一段【多行】JD：贴完敲空行提交；直接空行=结束 ============
def read_one_jd():
    print("\n── 粘贴一段 JD（多行没关系），贴完单独敲一个【空行】回车提交；"
          "什么都不输直接空行 = 全部结束 ──")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:            # Ctrl+Z 回车（Win）也能收尾
            break
        if line.strip() == "":      # 空行 = 这段结束
            break
        lines.append(line)
    return "\n".join(lines).strip()  # strip 去掉整段首尾空白；中间换行保留


# ============ 5. 主循环：一段一段读、抽取、即时落盘 ============
if __name__ == "__main__":
    count, ok = 0, 0
    while True:
        jd = read_one_jd()
        if not jd:                  # 空 → 用户想结束
            break
        count += 1
        print(f"[{count}] 解析中……")
        data = extract_jd(jd)
        if data is None:
            print("    ✗ 放弃（重试 3 次仍失败）")
            continue
        save_to_csv([data])         # 每条立刻写盘，中途崩了也不丢已完成的
        ok += 1
        print(f"    ✓ {data.get('title')} @ {data.get('city')}  {data.get('salary')}")

    print(f"\n完成：{ok}/{count} 条合法，已写入 jobs.csv")
