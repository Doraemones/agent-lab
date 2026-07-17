# Agent 开发执行手册（逐日版）

> 配套之前的《学习路线》使用。这份是"导航"：每天做什么、用哪个资源的哪一章、产出什么文件、达到什么标准才算过关。
> 格式约定：每天分【学】【做】【过关标准】。过关标准没达到，就不要往下走，宁可慢一天。
> 日期按 7/4 启动排的，往后顺延也没关系，但 **8/9"项目一上线+简历投出"这个节点不能动**。

---

## 阶段 0：环境与账号（7/4-7/5 周末，共半天）

按顺序做完打勾：

- [x] 安装 Python 3.11+（用 Miniconda 或 uv）、VS Code、Git
- [x] 注册 GitHub 账号，新建仓库 `agent-lab`，克隆到本地。**之后所有代码都放这个仓库，每天至少 1 次 commit**——这个仓库 3 个月后就是你简历上的 GitHub 链接
- [x] 注册 DeepSeek 开放平台（https://platform.deepseek.com），充 10 元；或注册硅基流动（https://siliconflow.cn，送额度，还提供 embedding 和 rerank 接口，后面要用）
- [x] 写第一个脚本 `00_hello.py`：用 openai SDK（兼容 DeepSeek）调一次对话接口，打印回复
- [x] 注册力扣（https://leetcode.cn），做第 1 题（两数之和）
- [x] fork 并 star：`datawhalechina/hello-agents`、`datawhalechina/llm-universe`，把在线阅读地址存书签

**过关标准**：`00_hello.py` 运行成功；仓库有第一次 commit；API 余额页面能看到调用记录。

---

## 第 1 周（7/6-7/12）：把 API 玩到熟练——Agent 的原子能力

本周不碰任何框架。目的：以后用框架时你知道底层发生了什么，面试被问到才不慌。

### Day 1（周一）：多轮对话与消息结构
- 学：llm-universe C2《使用 LLM API 开发应用》前半部分（1.5h）｜在线阅读：https://datawhalechina.github.io/llm-universe/
- 做：`01_chat.py`——命令行聊天机器人。while 循环读输入，维护 `messages` 列表（含 system prompt），支持 `/clear` 清空、`/exit` 退出
- 过关标准：
  - 聊 10 轮不丢上下文（第 10 轮问"我第一句说了什么"能答对）
  - 能口头解释 system / user / assistant / tool 四种 role 各自的作用
  - 能说出 temperature、max_tokens 是什么，temperature=0 和 1.5 各适合什么场景

### Day 2（周二）：流式输出与上下文管理
- 学：DeepSeek/OpenAI 文档的 streaming 章节（0.5h）｜DeepSeek 文档：https://api-docs.deepseek.com/
- 做：给 `01_chat.py` 加 `stream=True` 逐字打印；记录每轮 usage 的 token 数，当历史超过 4000 token 时自动丢弃最早的对话轮
- 过关标准：
  - 能解释为什么产品都用流式（首 token 延迟 vs 总时长）
  - 能说出上下文装不下时的 3 种策略：截断、摘要压缩、检索（这是第 2 周 RAG 的伏笔）

> **📝 我的复盘笔记（Day 2）**
>
> **过关标准作答：**
> 1. **为什么用流式**：非流式要干等「总时长」（长回复十几秒盯空白屏，像卡死）；流式把**首 token 延迟(TTFT)**降到几百 ms，字一出现就能读——**总时长几乎没变，降的是感知延迟**。且人读字通常慢于模型生成，读着读着就生成完了，几乎无等待感；附带好处：看跑偏可 early stop 省 token。
> 2. **上下文装不下的 3 策略**：①**截断**——丢最早的对话轮（最简单，今天做的就是它，缺点=真忘掉早期信息）；②**摘要压缩**——把早期对话让模型压成一段摘要再塞回（省 token 保大意，但丢细节+多一次调用）；③**检索(RAG)**——历史/文档进向量库，每轮只按当前问题检索最相关几段（第 2 周伏笔）。
>
> **实现踩坑（stream=True）：**
> - 正文在 `delta.content`（不是非流式的 `message.content`）；想记 usage 必须加 `stream_options={"include_usage": True}`，且 usage 只在**最后一个 `choices` 为空**的 chunk 里。
> - `for chunk in resp` 是**阻塞式**：`next()` 嘬不到数据就原地等，消费端追不过生产端，**不会**打印一半就截断。resp 只是「插进服务器的吸管」，返回时一个字都还没生成，真正生成的是服务器。
> - 循环结束靠 `finish_reason`（`stop`=自然说完 / `length`=被 max_tokens 砍断）+ `[DONE]`。**max_tokens 是服务器踩的刹车，砍断时照发终止信号，不会因回复过长而无限阻塞**；真正卡死只有网络失联 → 靠 `client(timeout=…)` 兜底。
> - `try/except` 要**包住 for 循环本身**；只包在 `create()` 上接不住流式中途的网络错误（数据是在循环里懒加载的）。

### Day 3（周三）：结构化输出
- 学：JSON mode / response_format 文档（0.5h）｜DeepSeek JSON 输出：https://api-docs.deepseek.com/guides/json_mode
- 做：`02_extract.py`——输入一段招聘 JD 文本，输出严格 JSON：`{岗位名, 技能要求[], 薪资, 城市, 学历要求}`。用 `json.loads` 校验，解析失败自动重试（最多 3 次）
- 过关标准：从 BOSS/牛客随便复制 20 条真实 JD，20/20 输出合法 JSON。这个脚本顺手帮你干正事：把提取结果存 `jobs.csv`，就是你的投递情报库

### Day 4-5（周四五）：Function Calling ⭐ 本周核心
- 学：DeepSeek 或 OpenAI 的 function calling 官方文档，通读两遍（2h）｜DeepSeek Function Calling：https://api-docs.deepseek.com/guides/function_calling
- 做：`03_tool_loop.py`——**纯 SDK，不用任何框架**，写完整工具调用循环：
  1. 定义 3 个工具：`get_current_time`（真实现）、`calculator`（用 `eval` 前先做安全过滤或用 `ast`）、`search_web`（可先 mock 返回假数据）
  2. 主循环：发请求 → 若返回 `tool_calls` → 本地执行函数 → 结果以 `role="tool"` 消息追加 → 再发请求 → 直到模型给出最终文本答案
- 过关标准：
  - 提问"现在几点？帮我算一下距离 8 月 9 日还有多少小时"能触发**连续两次**工具调用并答对
  - 能在纸上画出完整时序图（用户→模型→你的代码→函数→模型→用户）
  - 能回答面试高频题："模型真的执行了函数吗？"（没有。模型只输出调用意图 JSON，执行发生在你的代码里，这就是为什么工具的安全边界由你负责）

### Day 6（周六）：手写 ReAct ⭐
- 学：hello-agents 第四章《智能体经典范式构建》（2h，跟着敲）｜在线阅读：https://datawhalechina.github.io/hello-agents/
- 做：`04_react.py`——不用 function calling 接口，纯 prompt 实现：提示词里规定 `Thought:/Action:/Action Input:/Observation:` 格式，用正则解析模型输出的 Action，执行后把 Observation 拼回 prompt 继续循环
- 过关标准：
  - 能完成需要 3 步以上的任务（如"搜索 X，基于结果计算 Y，再总结"）
  - 能回答："ReAct 和原生 function calling 什么区别？各自什么时候用？"（ReAct 是 prompt 层范式、模型无关但解析脆弱；FC 是训练进模型的能力、可靠但依赖模型支持）
  - 遇到过至少一次"模型不按格式输出导致解析失败"，并且你加了处理（这个坑面试可以讲）

### Day 7（周日）：复盘日
- 给仓库写 README：每个脚本一句话说明 + 运行方法
- 本周力扣应累计 7 题（数组、哈希表起步）
- **周自测**（答不上的回去补，口头答，最好录音听回放）：
  1. 一次完整的 function calling 交互，HTTP 层面发生了几次请求？
  2. messages 里 tool 消息的 `tool_call_id` 是干嘛的？
  3. 为什么 system prompt 放开头而不是每轮重复？
  4. token 是什么？中文一个字大概几个 token？
  5. ReAct 循环最大的工程风险是什么？（死循环——所以要设最大步数）

---

## 第 2 周（7/13-7/19）：RAG——从 Embedding 到能用的知识库问答

选一份你自己的材料做实验语料（推荐：你研究方向的一篇 30+ 页中文综述，或者你的毕业论文开题材料）。用自己熟的领域，好坏一眼能判断。

### Day 8（周一）：Embedding 直觉
- 学：llm-universe C3 第 1-2 节（1h）｜在线阅读：https://datawhalechina.github.io/llm-universe/
- 做：`05_embed.py`——挑 20 个句子（10 个你领域的、10 个无关的），调 embedding API（硅基流动 bge-m3 免费），两两算余弦相似度，打印矩阵
- 过关标准：验证"语义相近的句子分数高"；能解释 embedding 是什么、这个模型输出多少维、余弦相似度公式

### Day 9（周二）：文档加载与切分
- 学：llm-universe C3 第 3 节（1h）｜在线阅读：https://datawhalechina.github.io/llm-universe/
- 做：`06_loader.py`——用 pypdf 或 unstructured 加载你的 PDF，实现两种切分：固定 500 字+100 重叠 / 按标题分段，输出切块统计（块数、平均长度）
- 过关标准：肉眼检查 10 个块，没有"句子被拦腰砍断导致语义残缺"的严重情况；能说出 3 种切分策略和适用场景（固定长度/结构感知/语义切分）

### Day 10（周三）：向量库
- 学：llm-universe C3 第 4 节（https://datawhalechina.github.io/llm-universe/）；Chroma 官方 quickstart（1h）｜Chroma：https://docs.trychroma.com/
- 做：`07_vectordb.py`——切块入 Chroma；设计 10 个测试问题（5 个能在文档找到答案、3 个部分相关、2 个完全无关），逐个检索 top-5，人工标注召回质量
- 过关标准：产出 `retrieval_notes.md`，记录哪些问题召回差、你猜的原因（切分问题？表述差异？）。**这份笔记就是面试素材**

### Day 11（周四）：完整 RAG 问答
- 学：llm-universe C4《构建 RAG 应用》（1.5h）｜在线阅读：https://datawhalechina.github.io/llm-universe/
- 做：`08_rag.py`——检索 top-5 → 拼入 prompt → 生成答案 → **末尾列出引用的原文片段编号**。Prompt 里明确约束："仅根据以下资料回答，资料中没有的信息回答'资料中未提及'"
- 过关标准：
  - 10 个测试问题 ≥7 个回答正确且引用对
  - 2 个无关问题，模型老实说"未提及"而不是编造
  - 能解释你是怎么用 prompt 压幻觉的

### Day 12（周五）：Rerank
- 做：`09_rerank.py`——检索改成两段式：向量粗召回 top-20 → rerank 模型（硅基流动 bge-reranker API）精排取 top-5。同样 10 问跑一遍
- 过关标准：产出对比表（rerank 前后各命中几问）。能解释为什么 rerank 有效（双塔 embedding 只算粗相似，交叉编码器逐 token 对比 query 和文档，精度高但慢，所以只用在小候选集上）

### Day 13（周六）：评估
- 学：llm-universe C5《系统评估与优化》+ RAGAS 文档首页概念部分（1.5h）｜llm-universe：https://datawhalechina.github.io/llm-universe/ ｜RAGAS：https://docs.ragas.io/en/stable/
- 做：把测试问题扩到 30 个存 `eval.jsonl`（含标准答案要点）；写 `10_eval.py`：用一个强模型当裁判（LLM-as-judge），自动判每个回答是否覆盖要点，输出得分
- 过关标准：跑通全自动评估，得到一个基线分数（比如 30 题对 21，70%）。**记住这个数，项目一里你要复用这套方法并展示"优化后从 X% 到 Y%"**

### Day 14（周日）：复盘日
- 力扣累计应达 14 题
- **本周终极自测**：找一张白纸，不看任何资料，画出 RAG 完整链路（加载→切分→embedding→入库→检索→rerank→拼 prompt→生成→评估），每一环写出"我用的方案 + 至少一种替代方案"。画不出来 = 本周没过关。这是中厂面试的原题级考点

---

## 第 3 周（7/20-7/26）：LangGraph + 项目一选题

### Day 15-16（周一二）：LangGraph 入门
- 学：LangGraph 官方 quickstart 教程（https://docs.langchain.com/oss/python/langgraph/quickstart）跟敲；中文可配 hello-agents 第六章 LangGraph 部分（https://datawhalechina.github.io/hello-agents/）
- 做：`11_langgraph_agent.py`——把第 1 周的 tool_loop 用 LangGraph 重写：StateGraph + 一个 agent 节点 + 一个 tools 节点 + 条件边
- 过关标准：能解释 State 是什么、怎么在节点间传递；能说出"用 LangGraph 比裸写 while 循环多得到了什么"（状态持久化、可视化、中断恢复、条件路由）

### Day 17（周三）：记忆与人工介入
- 做：给昨天的 agent 加 checkpointer（先用 MemorySaver，再换 SqliteSaver）实现"程序重启后恢复对话"；再加 interrupt：执行某个"危险工具"前暂停等用户确认
- 过关标准：两个功能都演示得出来；能解释 thread_id 的作用

### Day 18（周四）：横向视野 + 上下文工程
- 学：hello-agents 第六章通读（AutoGen、AgentScope 是什么，不用会写，面试能对比即可）+ 第九章《上下文工程》（2.5h）｜在线阅读：https://datawhalechina.github.io/hello-agents/
- 过关标准：
  - 能答"多智能体什么时候真的有必要？"（角色分工/上下文隔离/并行，而不是为多而多——面试官喜欢听你反对过度设计）
  - （2026-07-15 增补）能用自己的话讲**上下文工程四类操作：write（写入外部）/ select（选取入窗）/ compress（压缩）/ isolate（隔离）**，各举一例——你 Day 2 的截断/摘要/检索三策略就是它的雏形。行业现状：这个词已基本取代 prompt engineering，是面试新热词；另一句要能接：**"agent 的失败多是状态管理失败，而非提示词失败"**

### Day 19-21（周五-周日）：项目一设计 ⭐（选题已定）

**项目一：古诗词视频全自动生产 Agent**——输入一首诗，输出带吟诵、字幕、配画的成片。定位说清楚：这是"多模态内容生产 Agent 系统"，不是"做短视频账号"；账号发布只是上线证据。

**为什么它是 agent 而不是固定流水线**（面试必答，背下来）：每句诗的处理路径不确定——生成的画面可能不匹配意象需要改写重试、不同诗句值得不同成本的镜头方案，这些决策由模型根据中间结果动态做出，而非写死的 pipeline。

**技术选型（省钱版，全部低成本可跑）**：

| 环节 | 首选 | 说明 |
|---|---|---|
| 编排 | LangGraph | 主图 + 每句诗一个子图 |
| LLM（解析/分镜） | DeepSeek | 已有账号 |
| 意象/典故 RAG | 第 2 周管线复用 | 语料：诗词赏析资料、意象词典 |
| 文生图 | 硅基流动 Kolors 等低价模型 | MVP 阶段够用 |
| VLM 质检 | Qwen-VL / GLM-4V | 审图：画面与诗句意象匹配度 |
| 图生视频 | 可灵/Vidu API，**只给关键镜头** | MVP 可完全不用，纯静态+运镜 |
| TTS 吟诵 | edge-tts（免费）起步 | 进阶再换 CosyVoice |
| 合成 | ffmpeg（运镜/字幕/混音） | 胶水代码，放心让 AI 写 |

- 做：写 `design.md`：用户故事、mermaid 状态图（**必须画出质检反思环和成本路由分支**）、State 字段设计（诗句列表、各句素材路径、重试计数、成本累计）、工具清单（每个工具的输入输出）、评估指标定义（一次通过率/平均重试/单条成本/耗时）
- 过关标准：状态图里能指出"哪个箭头是 agent 在做决策"；MVP 范围明确写死——**五言/七言绝句（4 句）、静态图+运镜为主、质检环只做图片**。范围之外的想法全部记进 `v2_ideas.md`，8/9 前禁止碰

---

## 第 4-5 周（7/27-8/9）：项目一从 0 到上线

不再逐日，按里程碑推进（顺序固定，每个 1-3 天）。**每完成一个 M 就 commit + 在 README 更新进度**。

> **⭐ 评估前置原则（2026-07-15 增补）**：20 首绝句评估集 + 指标口径（一次通过率/平均重试/单条成本/耗时）在 **M0-M1 就建好并跑出第一版基线**，M2/M3/M4 每个里程碑都复跑一遍对比，M6 只做汇总展示。业界现行原则：**评测是基础设施，先建评测台再谈优化**——demo 和产品的分水岭就在这，别把评估留到收尾。

| 里程碑 | 做什么 | 过关标准 |
|---|---|---|
| M0 技术验证（2天） | 不管架构，先打通**单句**最小链路：一句诗 → LLM 分镜 prompt → 文生图 → edge-tts → ffmpeg 合成 5 秒带字幕片段 | 一条命令出第一个"能看"的片段；产出 `cost.md`（每个 API 单价、单条视频成本预估）。**成本算不过来就在这里改方案，别到 M4 才发现** |
| M1 编排主图（2天） | LangGraph：解析诗歌 → 逐句子图（分镜→生图→合成）→ 总装拼片。State 按 design.md 实现 | 输入任意绝句，端到端自动出完整视频（质量先不管）；中途断掉能从 checkpoint 恢复 |
| M2 意象 RAG（2天） | 意象/典故语料入库；分镜 prompt 生成前检索注入 | 对比实验：挑 10 句含典故的诗句，带检索 vs 不带，人工评分镜准确性，数据记入 README（防"床前明月光画成现代床"就是这步的卖点） |
| M3 质检反思环 ⭐（2天） | VLM 审图节点：诗句+意象要点+图 → 匹配度评分+问题描述 → 不合格改写 prompt 重试（≤2次）→ 仍败则降级（水墨底图+书法字卡） | 能现场演示一个真实案例：错图→自动改写→通过；统计出一次通过率基线 |
| M4 成本路由（1天） | 路由节点：每句判定用"静态图+运镜"（默认）还是图生视频（只给全诗 1-2 个名场面句）；成本累计进 State | 能说出一首诗里每句走了哪条路、为什么；单条成本 ≤ 你在 M0 定的预算 |
| M5 服务化+部署（2天） | FastAPI：`POST /generate` 提交诗 → 后台任务 → SSE 进度推送 → 成片下载；一页 Web 表单；Docker 化部署（demo 环境默认"低成本模式"） | 别人在网页贴一首绝句，几分钟后拿到视频 |
| M6 评估+包装（3天） | 20 首绝句批量评估：一次通过率/平均重试/单条成本/平均耗时，做一轮优化记录 before→after；README（架构图+指标表+3 个样片 GIF）；录 2 分钟 demo；**挑最好的 3 条发布到账号**（B站/小红书/抖音任选） | README 齐全；账号有 3 条已发布作品作为"上线证据" |

**项目一整体验收清单**（全过才算完成）：
- [ ] 在线 demo：输入任意五言/七言绝句，产出带吟诵、字幕、配画的成片
- [ ] 质检反思环有可现场演示的真实案例（错图→改写→通过）
- [ ] 意象 RAG 有对比数据（带/不带检索）
- [ ] 成本路由讲得清：每句走哪条路、为什么、单条成本数字
- [ ] 指标表：一次通过率 X%、平均重试 Y 次、单条成本 Z 元、耗时 W 分钟（真实比好看重要，"58%→85% 的优化过程"比"98%"更打动面试官）
- [ ] 账号已发布 ≥3 条成片（上线证据，粉丝数无所谓）
- [ ] 你能对着状态图讲 10 分钟设计取舍，不看稿

### ⭐ 8/9 硬节点：简历 v1 + 开投
项目段落照这个模板写（一段 3-4 行）：

> **诗境 · 古诗词视频生成 Agent（个人项目）** ｜ LangGraph / 多模态 / RAG / FastAPI / Docker
> 独立设计并上线了古诗词视频全自动生产智能体：基于 LangGraph 编排"诗歌解析→意象检索（RAG）→分镜生成→文生图→VLM 质检→TTS 吟诵→ffmpeg 合成"多模态工具链；设计质检反思环（VLM 审图不合格自动改写 prompt 重试+降级），一次通过率从 X% 提升至 Y%；实现成本感知路由（静态运镜/视频生成分级调用），单条成本降至 Z 元；FastAPI + SSE 进度推送，Docker 部署，作品已在 XX 账号发布。在线 demo：xxx

投递动作（从 8/9 起每天固定 40 分钟）：
- 牛客 + 各公司官网 + BOSS 直聘，每天投 10-15 家；建 `投递记录.xlsx`（公司/岗位/日期/状态/面经链接）
- 岗位关键词搜：`大模型应用`、`AIGC 应用`、`Agent 开发`、`LLM 工程师`、`AI 应用开发`（别只搜"agent"，很多中厂岗位名五花八门）
- 用小林coding校招汇总表跟踪开投时间：https://www.xiaolincoding.com/other/ocoffer.html

---

## 第 6 周（8/10-8/16）：MCP + 第二个可展示物

- 学：Hugging Face MCP Course unit 0-1（https://huggingface.co/learn/mcp-course/en/unit0/introduction）（或 hello-agents 第十章：https://datawhalechina.github.io/hello-agents/）（3h）
- 做（二选一，或先 1 后 2）：
  1. 给项目一接入一个现成 MCP server（如 fetch/文件系统类），证明你会集成
  2. **自己写一个小 MCP server 并独立开源**：候选——arxiv 论文检索、牛客/力扣每日一题查询、你领域的某个数据源。工作量 1-2 天，但"发布过 MCP server"在简历上辨识度很高
- 过关标准：能答"MCP 解决什么问题？和 function calling 什么关系？"（FC 是模型层的调用机制；MCP 是工具接入的标准化协议层，让工具写一次、所有支持 MCP 的应用都能用——类比 USB 接口）
- 本周起节奏切换：学习 2h + 八股 1h + 力扣 1h + 投递 40min

---

## 第 7-8 周（8/17-8/30）：八股系统化 + 笔试期

每天：八股 2h + 力扣 1.5h + 投递/笔试 + 项目小修。

### 八股范围（就这四类，别扩）
资料源：AgentGuide 题库（https://github.com/adongwanai/AgentGuide）+ hello-agents 仓库 Extra-Chapter 的面试题两篇（https://github.com/datawhalechina/hello-agents/tree/main/Extra-Chapter）。

**A. Transformer 与 LLM 基础（约 15 问）**
Attention 公式与直觉、为什么除以 √d、多头的作用、KV Cache 是什么为什么能加速、位置编码（RoPE 概念）、解码策略（greedy/top-p/temperature）、预训练 vs SFT vs RLHF 各阶段干嘛、幻觉成因、上下文窗口为什么有限。

**B. RAG（约 12 问）**
完整链路白板题、切分策略取舍、embedding 模型怎么选、为什么要 rerank、召回差怎么排查、RAG vs 微调 vs 长上下文怎么选（高频！）、多路召回、如何评估 RAG、生产中怎么处理文档更新。

**C. Agent（约 15 问）**
Agent 定义与和工作流的区别、ReAct 原理与缺陷、function calling 全流程、planning 范式、反思机制、多智能体的适用与滥用、记忆怎么设计（短期/长期/何时写入）、MCP、agent 怎么评估、死循环/工具失败怎么处理、上下文工程是什么（含 write/select/compress/isolate 四类操作）、为什么说"agent 的失败多是状态管理失败而非提示词失败"、成本延迟怎么优化。

**D. 微调概念（约 8 问，只要说得清，不要求实操）**
SFT 是什么、LoRA 原理（低秩分解，训练参数量为什么少）、全参 vs LoRA、RLHF 三阶段、DPO 相对 PPO 简化了什么、什么时候该微调什么时候 prompt 就够（高频！）。

- 过关标准：50 问每问录音自答 1-2 分钟不卡壳。答不出的写进 `八股弱点.md`，隔天重答
- 力扣：本周结束累计 60-70 题（按 hot100 顺序：哈希→双指针→滑窗→子串→数组→链表→二叉树）

---

## 第 9-12 周（8/31-9/27）：面试冲刺期

每天：模拟/真实面试复盘 2h + 力扣 1h + 八股查漏 1h + 持续投递。

### 项目深挖 15 问（每问写 150-300 字答案，背到能自然说出）
1. 整体架构讲一下？（2 分钟版本和 30 秒版本各备一个）
2. 为什么用 LangGraph 不用裸写循环/不用 Dify？
3. 状态里存了什么？为什么这么设计？
4. 工具调用失败你怎么处理的？演示过最极端的失败是什么？
5. 怎么防止 agent 死循环？
6. RAG 为什么要两段式检索？rerank 带来多少提升，数据呢？
7. 你的评估集怎么构建的？指标怎么定义的？
8. 印象最深的 bad case 是什么？怎么修的？（必考，提前挑 2 个故事）
9. 一次请求的延迟大概多少？瓶颈在哪？怎么优化过？
10. Token 成本多少？做过什么省钱设计？
11. 如果并发 100 用户，你的架构哪里先崩？
12. 幻觉问题在你项目里怎么体现的？怎么压的？
13. 为什么这个场景需要 agent 而不是固定 pipeline？
14. 如果让你重做，你会改什么？
15. 这个项目和生产级系统的差距在哪？（诚实+具体=加分）

针对诗词视频项目再加 3 问：
16. VLM 质检的判据怎么设计的？它自己会不会误判，你怎么发现和处理的？
17. 质检不通过时的 prompt 改写策略是什么？（原图问题描述怎么反馈进新 prompt）
18. 多句画面的风格/人物一致性怎么保证的？（风格锚定 prompt/参考图；答不好就诚实说这是 v2 待解——但要说得出候选方案）

### 其余动作
- 每周 ≥1 次模拟面试：同学互面 / 牛客 AI 模拟面试 / 自己对着手机录 20 分钟自述后回放挑毛病
- 每场真实面试当晚复盘：所有问题记入 `面经.md`，答不上的 24 小时内补齐——面过 5 家后你的题库覆盖率会指数上升
- 力扣冲到 100-120 题；手撕高频单独准备：LRU 缓存、快排、二叉树层序、topK、反转链表
- 9 月下旬若有余力：hello-agents 第 11 章（Agentic RL，https://datawhalechina.github.io/hello-agents/）通读，面试聊到训练话题能接住，作为差异化加分

---

## 贯穿全程的 4 条规则

1. **每日模板**：学习/项目 3h + 力扣 30-45min + 5min 在 `log.md` 记一行"今天做了什么、卡在哪"。毕业论文时间自行另排，但上面这 4 小时是底线。
2. **20 分钟法则**：卡住超过 20 分钟 → 问 AI / 搜 GitHub issue → 再不行标记 TODO 跳过，周日复盘日统一处理。禁止一个 bug 耗一晚上。
3. **手写 vs AI 生成的边界**（判断标准：这段代码是不是面试考点）：
   - **纯手写第一遍**：第 1-3 周核心脚本（tool loop、ReAct、RAG 链路、LangGraph 状态图）。写到能跑后再让 AI review 挑毛病。这些代码本身就是面试题，你踩的坑就是你的答案。
   - **放心让 AI 写**：Dockerfile、FastAPI 模板、Streamlit 页面、argparse 等胶水样板，无面试价值。
   - **项目阶段（第 4 周起）结对模式**：你当架构师（状态图、工具接口、关键逻辑自己定），AI 当实习生生成具体实现，**每段合并前你必须能逐行解释**。面试聊"如何用 AI 提效"时这就是素材。
   - **力扣必须纯手写**：笔试和手撕环节没有 AI。
   - 自测法：“面试官删掉这段让我白板重写，我写得出核心逻辑吗？”写不出=学习被外包了。
   - AI 的加分用法：解释报错、review 代码指出 3 个问题、"出 5 道 function calling 面试题考我"、把你的口头回答批改成更专业的表述。
4. **周日自查制**：每周日对照本手册的过关标准逐条打勾，没过的挪入下周并压缩新内容。进度可以慢，但不可以自欺。

---

## 快速索引：所有资源

**主线中文教程**

| 资源 | 用在 | 链接 |
|---|---|---|
| llm-universe | 第 1-2 周（C2→Day1，C3→Day8-10，C4→Day11，C5→Day13） | GitHub：https://github.com/datawhalechina/llm-universe ｜ 在线阅读：https://datawhalechina.github.io/llm-universe/ |
| hello-agents | 第 1、3、6 周 + 面试题（四章→Day6，六/九章→Day15-18，十章→第6周，Extra→第7-8周，11章→9月） | GitHub：https://github.com/datawhalechina/hello-agents ｜ 在线阅读：https://datawhalechina.github.io/hello-agents/ ｜ 面试题：https://github.com/datawhalechina/hello-agents/tree/main/Extra-Chapter |

**API / 工具官方文档**

| 资源 | 用在 | 链接 |
|---|---|---|
| DeepSeek API 文档 | 第 1 周（Day2 流式 / Day3 JSON / Day4-5 FC） | 首页：https://api-docs.deepseek.com/ ｜ JSON 输出：https://api-docs.deepseek.com/guides/json_mode ｜ Function Calling：https://api-docs.deepseek.com/guides/function_calling |
| DeepSeek 开放平台（账号/充值） | 已注册 | https://platform.deepseek.com |
| 硅基流动（embedding/rerank API） | 第 2 周起 | https://siliconflow.cn |
| Chroma 向量库 | 第 2 周（Day10） | https://docs.trychroma.com/ |
| RAGAS 评估 | 第 2 周（Day13） | https://docs.ragas.io/en/stable/ |

**框架 / 协议**

| 资源 | 用在 | 链接 |
|---|---|---|
| LangGraph 官方教程 | 第 3-5 周 | Quickstart：https://docs.langchain.com/oss/python/langgraph/quickstart ｜ 仓库：https://github.com/langchain-ai/langgraph |
| HF MCP Course | 第 6 周 | https://huggingface.co/learn/mcp-course/en/unit0/introduction |
| HF Agents Course（补充） | 有余力 | https://huggingface.co/learn/agents-course/en/unit1/introduction |

**面试 / 投递**

| 资源 | 用在 | 链接 |
|---|---|---|
| AgentGuide 面试题库 | 第 7-12 周 | GitHub：https://github.com/adongwanai/AgentGuide ｜ 网页：https://adongwanai.github.io/AgentGuide/ |
| 小林coding 校招汇总 | 8 月起投递 | https://www.xiaolincoding.com/other/ocoffer.html |

**拓展阅读（有余力再看）**

| 资源 | 用在 | 链接 |
|---|---|---|
| Anthropic《Building Effective Agents》 | agent 设计取舍 | https://www.anthropic.com/research/building-effective-agents |
| Agent-Learning-Hub（路线库） | 拓展 | https://github.com/datawhalechina/Agent-Learning-Hub |
| deepagents-in-action（生产级实战） | 拓展 | https://github.com/datawhalechina/deepagents-in-action |

*生成日期 2026-07-03。按你的实际开始日期整体平移即可，唯一不可平移的是"8 月上旬必须开始投递"。*
*链接核实并补全：2026-07-05。两处订正：LangGraph 官方文档已迁移至 docs.langchain.com；hello-agents 在线阅读用 datawhalechina.github.io/hello-agents/（原 hello-agents.datawhale.cc）。*
*2026-07-15 结合行业检索微调三处：①评估前置原则（第 4-5 周里程碑表前）；②上下文工程四类操作与"状态管理失败"提法（Day 18 过关标准）；③八股 C 类补两问。检索结论：原手册与 2026 行业共识高度一致（evals 当基础设施、上下文工程、MCP、状态管理均已覆盖），故结构与 8/9 节点均不动。*
