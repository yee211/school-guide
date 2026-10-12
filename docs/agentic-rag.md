# Agentic RAG

当前入口仍为 POST /chat 和 POST /chat/stream，前端和 SSE delta/done.sources 协议不变。

## 链路

QueryRouter 优先处理单个目标的简单分数/计划问题，直接查结构化表；混合问题、多专业对比及开放问题进入 AgenticRAG。多轮问题只改写一次，原问题保留用于最终回答，改写最多等待 6 秒。结构化快查询最多等待 10 秒，无有效结果或失败时进入 Agent。

Agent 每轮用绑定工具的意图模型检查已返回证据，选择 query_admission_data 或 search_school_knowledge，并决定补查或结束。文档工具复用现有向量 + BM25 + RRF + Qwen Rerank。结构化工具复用现有 PostgreSQL/Redis 查询，不执行模型生成的 SQL。

没有工具调用且没有查过资料时，强制执行一次文档检索，避免规划模型直接用记忆回答。重复工具名和规范化参数复用请求内缓存。证据按片段或完整结构化行去重；最终 sources 只来自实际纳入的证据。规划输出不会进入回答证据。

完成后使用新消息列表调用原有流式生成，提示回答缺失项、年份与冲突。空查询结果也可交给最终回答器说明缺失条件；在超时且完全没有可用结果时返回现有固定兜底。

## 配置

| 环境变量 | 默认值 | 含义 |
|---|---:|---|
| AGENT_MAX_ROUNDS | 3 | 规划模型调用次数上限，限制为 1–10 |
| AGENT_MAX_TOOL_CALLS | 6 | 请求内工具尝试次数上限，重复和无效调用也计数，限制为 1–20 |
| AGENT_TIMEOUT_SECONDS | 25 | Agent 检索阶段总等待预算 |
| AGENT_STEP_TIMEOUT_SECONDS | 10 | 单次规划或工具等待上限 |
| AGENT_CONTEXT_CHARS | 12000 | 纳入最终上下文的证据字符预算，不含标题标记与历史 |

整体请求还包括路由、历史改写和最终回答生成；25 秒不是端到端请求超时。同步 PostgreSQL 查询使用 asyncio.to_thread，等待超时不会终止已开始的数据库线程。规划器每次结果预览最多 6000 字符，最终事实证据按完整片段/表格行纳入预算，不截断数字行。学校系统提示词仍要求精确数字以结构化数据为准。

## 验证

在项目根目录设置 PYTHONPATH=backend，运行：

```powershell
$env:PYTHONPATH='backend'
.venv/Scripts/python.exe -m unittest backend.scripts.test_query_router backend.scripts.test_agentic_rag
```

离线测试覆盖多工具补查、空结果、重复去重、预算、超时、工具失败、规划失败、快通道、结构化行来源以及 SSE 协议。

上线前用真实模型与数据库评估：单轮分数、湖南等补充追问、多专业学费/人数/就业对比、指定年份缺失、资料冲突。对比事实准确率、子问题覆盖率、来源一致性、首字延迟和模型调用数。复合问题增加独立的结构化覆盖检查；尚未实现生成后逐句事实核验器。

## 本轮问答优化

- 分数/报考问题条件不足时先追问年份、省份、科类和专业/专业组；先结合多轮历史补全，只追问缺失项。追问直接返回 SSE，不消耗回答模型请求。历年趋势、全国汇总、概念说明不强制追问。
- 已知专业 × 请求指标 × 精确数据的年份/省份/科类生成需求清单（最多20项）；目前是规则提取，无法覆盖任意自然语言需求。
- 复合问题使用意图模型的结构化输出做逐项覆盖检查，必须提供实际证据ID。数值还要通过代码核对对应结构化列非空、专业/年份/省份/科类/专业组匹配，文档不能替代精确数据列。
- 缺失项在剩余预算内定向补查，独立项并行执行，重复请求仍被缓存拦截。核查与补查共享原有25秒检索预算；核查模型调用额外计费，但不计入3次规划调用上限。
- 最终提示词携带覆盖状态，要求明确列出未查到和未核验项。覆盖模型语义判断仍可能出错，这不是对回答准确性的保证。
- uvicorn日志打印 rounds/calls/evidence/coverage/elapsed_ms，可查看本次执行情况。

本轮未新增资料版本管理或来源预览界面。验证命令补充 backend.scripts.test_answer_requirements。

## 预设问题回归检查

在项目根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File backend/scripts/check_presets.ps1
```

或设置 `PYTHONPATH=backend` 后运行 `python -m unittest -v backend.scripts.test_knowledge_presets`。

检查直接读取前端 `knowledgeModules.ts` 的全部预设问题，并与 `backend/scripts/fixtures/knowledge_presets.json` 的预期证据契约对应：每个问题必须有契约、模块资料路径必须存在且位于 raw 目录、完整预设不得误触发招生追问、文档必须包含对应答案要点、结构化文件经实际解析后必须存在条件匹配且所需数值列完整的记录。2025年湖南物理类各组查询另检查六个组号和组级投档口径。

新增或修改预设时同步修改预期契约；删除资料、改错年份或丢失学费等字段会使检查失败。测试无需API密钥、Redis或数据库；这是源资料覆盖检查，不能替代真实检索、数据库同步和模型回答的端到端验证。

## 来源原文预览

知识导览资料标题与回答来源卡片可点击，在原生 dialog 中预览 Markdown 表格或文本；支持 Escape 关闭、键盘焦点约束和关闭后焦点恢复。Markdown 使用 DOMPurify 清理。加载时有状态提示，关闭时中止请求。

GET `/knowledge/source?source=data/raw/...` 同时接受导览的 `backend/data/raw/...` 路径，返回规范路径、标题、正文、截断标记。只允许 raw 目录内支持格式的真实文件，拒绝目录穿越及超过10MB的文件；预览最多60000字符并明确提示。PDF/Office附件复用现有解析器，展示提取文本；Markdown/文本按原文件读取。

这是文档原文预览，尚未做命中片段高亮或版本管理。检查命令补充 `backend.scripts.test_source_preview`。
