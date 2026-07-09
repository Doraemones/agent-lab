"""
- 做：`03_tool_loop.py`——**纯 SDK，不用任何框架**，写完整工具调用循环：
  1. 定义 3 个工具：`get_current_time`（真实现）、`calculator`（用 `eval` 前先做安全过滤或用 `ast`）、`search_web`（可先 mock 返回假数据）
  2. 主循环：发请求 → 若返回 `tool_calls` → 本地执行函数 → 结果以 `role="tool"` 消息追加 → 再发请求 → 直到模型给出最终文本答案
- 过关标准：
  - 提问"现在几点？帮我算一下距离 8 月 9 日还有多少小时"能触发**连续两次**工具调用并答对
  - 能在纸上画出完整时序图（用户→模型→你的代码→函数→模型→用户）
  - 能回答面试高频题："模型真的执行了函数吗？"（没有。模型只输出调用意图 JSON，执行发生在你的代码里，这就是为什么工具的安全边界由你负责）
"""


import os
import sys
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(find_dotenv())

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

def send_messages(messages):
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        tools=tools
    )
    return resp.choices[0].message

def get_current_time(timezone="UTC"):
    from datetime import datetime
    import pytz

    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S")

def calculator(expression):
    import ast
    import operator as op

    # 支持的运算符
    allowed_operators = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.USub: op.neg,
    }

    def eval_expr(expr):
        """
        安全地评估数学表达式
        """
        node = ast.parse(expr, mode='eval').body

        def _eval(node):
            if (
                isinstance(node, ast.Constant)
                and type(node.value) in (int, float)
            ):
                return node.value
            elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
                return allowed_operators[type(node.op)](_eval(node.left), _eval(node.right))
            elif isinstance(node, ast.UnaryOp):  # <operator> <operand> e.g., -1
                return allowed_operators[type(node.op)](_eval(node.operand))
            else:
                raise TypeError(f"Unsupported type: {type(node)}")

        return _eval(node)

    try:
        result = eval_expr(expression)
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"
    
def search_web(query):
    # 这里可以调用真实的搜索 API，或者 mock 返回假数据
    # 为了演示，我们返回一个固定的假结果
    return f"搜索结果：{query} 的相关信息（这是模拟数据）"


tools = [
    {
        "type":"function",
        "function":{
            "name":"get_current_time",
            "description":"获取当前时间",
            "parameters":{
                "type":"object",
                "properties":{
                    "timezone":{
                        "type":"string",
                        "description":"时区，默认 UTC"
                    }
                }
                ,
                "required":["timezone"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"calculator",
            "description":"执行数学表达式计算；需要数学运算时必须使用此工具",
            "parameters":{
                "type":"object",
                "properties":{
                    "expression":{
                        "type":"string",
                        "description":"数学表达式，例如 2 + 2 * (3 - 1)"
                    }
                },
                "required":["expression"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"search_web",
            "description":"搜索网页信息",
            "parameters":{
                "type":"object",
                "properties":{
                    "query":{
                        "type":"string",
                        "description":"搜索查询"
                    }
                },
                "required":["query"]
            }
        }
    }
]
## 工具分发函数
TOOLS_HANDLERS = {
    "get_current_time": get_current_time,
    "calculator": calculator,
    "search_web": search_web
}

def execute_tool(tool):
    #模型选择的工具名
    name = tool.function.name

    #模型返回的是JSON，转成字典
    arguments = json.loads(tool.function.arguments)

    #根据名称获取对应的python函数
    function = TOOLS_HANDLERS.get(name)

    if function is None:
        raise ValueError(f"未找到工具函数: {name}")

    #把字典参数展开传给函数
    result = function(**arguments)
    return str(result)

messages = [
    {
        "role": "system",
        "content": (
            "获取当前时间必须调用 get_current_time。"
            "所有数学运算必须调用 calculator，禁止自行计算。"
            "如果步骤有依赖，应依次调用工具。"
            "用户没有明确要求搜索网页时，不得调用 search_web。"
            "用户询问距离某月某日还有多少小时时，先获取当前时间，"
            "将未指定年份的日期解释为当前年份，并以该日 00:00 为目标时刻，"
            "再调用 calculator 完成时间差计算。"
        ),
    },
    {
        "role": "user",
        "content": "现在几点？帮我算一下距离 8 月 9 日还有多少小时",
    },
]

print(f"User: {messages[-1]['content']}")

max_turns = 10

for _turn in range(max_turns):
    message = send_messages(messages)

    # 先保存模型包含 tool_calls 的完整消息
    messages.append(message)

    # 没有工具调用，说明模型已经给出最终答案
    if not message.tool_calls:
        print(f"Model: {message.content}")
        break

    # 一轮响应可能包含多个工具调用，必须逐个执行
    for tool in message.tool_calls:
        print(f"[调用工具] {tool.function.name}")
        print(f"[工具参数] {tool.function.arguments}")

        result = execute_tool(tool)
        print(f"[工具结果] {result}")

        messages.append({
            "role": "tool",
            "tool_call_id": tool.id,
            "content": result,
        })
else:
    print("[达到最大轮数,强制停止]")