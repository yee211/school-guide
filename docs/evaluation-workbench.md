# 校园智答评测工作台

## 已完成
- 50 条检索案例：保留原来的 29 条，新增校园生活、图书馆等问法。离线检查来源文件及答案要点确实存在。
- 50 条回答案例：包含 8 条从本地资料实际解析的招生数字、多需求、历史追问、条件缺失、指定年份不存在和对抗输入。
- 相同检索 trace 对比语义排序、RRF 排序、重排排序的 Recall@K、MRR@K、NDCG@K、Hit@K。
- 单次混合文档检索与当前路由/Agentic RAG 对比；顺序交替，避免所有基线先跑造成单向缓存影响。
- 报告逐案例保存回答、来源、首字时间、总耗时、LLM 调用次数和供应商返回的 Token usage。
- 离线 CI：.github/workflows/evaluation-offline.yml。推送后才会在 GitHub 运行；目前只本地验证。

## 离线命令
在 backend 下，使用项目虚拟环境 Python：
```powershell
..\.venv\Scripts\python.exe -m unittest scripts.test_agentic_rag scripts.test_answer_requirements scripts.test_query_router scripts.test_knowledge_presets scripts.test_evaluation_contracts
..\.venv\Scripts\python.exe -m scripts.evaluate_retrieval_ab
..\.venv\Scripts\python.exe -m scripts.evaluate_answers
```

## 真实评测
显式加 --live 才使用 .env 中配置的 PostgreSQL、Redis、Embedding、Rerank 和 LLM；会把问题及检索到的学校资料发给供应商，产生调用费用。脚本只读查询，不重建索引，现有缓存可能被查询流程更新。不要把生产密钥写进 CI。
```powershell
..\.venv\Scripts\python.exe -m scripts.evaluate_retrieval_ab --live --limit 3
..\.venv\Scripts\python.exe -m scripts.evaluate_answers --live --limit 3
# 确认索引与来源契约有效后跑全量：
..\.venv\Scripts\python.exe -m scripts.evaluate_retrieval_ab --live
..\.venv\Scripts\python.exe -m scripts.evaluate_answers --live
```
报告默认放 evals/reports/，已忽略版本控制。每条回答完成后保存报告，便于中断后保留结果。

## 口径
- “single”是单次混合文档检索，不是历史版本的完整结构化路由。精确招生数据被排除出文档索引时，基线的数值不足是架构差异；不要据此宣称只加 Agent 就提升了数值准确率。
- 语义/融合/重排共用一次查询 trace；耗时属于整个 trace，不能当成三个独立方案的端到端耗时。
- 检索相关性采用“来源 + 词语存在”启发式，不是逐 chunk 人工标注。首次出现没有相关 chunk 的案例应检查分块和标签，不应偷偷放宽标签。
- keyword_facet_coverage 只是关键词覆盖；numeric_value_presence 只是数值出现，不能识别数字对应错专业或否定句。human_factual_correct / human_source_consistent 必须人工填写后才能报告事实正确率和来源一致性。
- 延迟是客户端进程墙钟时间，包括路由、历史改写、检索、规划和生成，不包括微信渠道。
- Token 仅记录 LLM 返回值，供应商不返回 usage 时不补零。cost 为 null，未提供模型价格；Embedding/Rerank 另行计费，不能把 LLM Token 当成全链路费用。
- 本地离线回归已验证；尚未运行真实模型/数据库评测，尚无性能收益结论。

## 人工复核与优化
逐案例确认：回答是否覆盖每个专业/指标；数字条件是否匹配；sources 是否支持对应事实；缺资料是否明确说缺失。保存失败类型，再选最多的一类优化，使用同一案例集复测，并记录准确性、延迟和调用量的取舍。单轮样本小，建议至少三次重复，再使用均值与 P95。
