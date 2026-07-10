"""
### Day 6（周六）：手写 ReAct ⭐
- 学：hello-agents 第四章《智能体经典范式构建》（2h，跟着敲）｜在线阅读：https://datawhalechina.github.io/hello-agents/
- 做：`04_react.py`——不用 function calling 接口，纯 prompt 实现：提示词里规定 `Thought:/Action:/Action Input:/Observation:` 格式，用正则解析模型输出的 Action，执行后把 Observation 拼回 prompt 继续循环
- 过关标准：
  - 能完成需要 3 步以上的任务（如"搜索 X，基于结果计算 Y，再总结"）
  - 能回答："ReAct 和原生 function calling 什么区别？各自什么时候用？"（ReAct 是 prompt 层范式、模型无关但解析脆弱；FC 是训练进模型的能力、可靠但依赖模型支持）
  - 遇到过至少一次"模型不按格式输出导致解析失败"，并且你加了处理（这个坑面试可以讲）
"""

import os
import sys
from openai import OpenAI
from dotenv import load_dotenv,find_dotenv

load_dotenv(find_dotenv())
api_key = os.getenv("DEEPSEEK_API_KEY")