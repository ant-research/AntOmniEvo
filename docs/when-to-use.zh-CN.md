# 适合什么场景

> [English](./when-to-use.md) · **中文**

只要满足两个条件——**(1) 被优化对象能用「可调文件目录」表达,(2) 评估可重复且相对便宜**——就能用 AntOmniEvo。被优化系统**不限于 LLM Agent**,常见形态按「可改的文件目录」分类:

- **AI Agent**(skill / harness / memory / extension 目录):NL2SQL skill、Terminal-Bench / SWE-bench 类 coding agent 的 skill+harness、AppWorld 类 agentic-API agent 的 skill、ReAct+RAG 的 system prompt + 策略文档。
- **Workflow / 流水线**(配置 + 节点代码):比如 retrieval DAG 的 `pipeline.json` + `nodes/*.py` + `extensions/*.json` + `skill/STRATEGY.md`;coding agent 可改 DAG 拓扑、改节点实现、调不变式。系统是否含 LLM 不影响框架,`System` 接口只认「可调产物 + 数据 → 轨迹 + 输出」。
- **单文件算法**(一个 `.py` / `.ts` + 它的描述):适合「算法本身可改、有评测集」的场景;`TunableArtifactSchema` 退化成「一个主算法文件 + 可选辅助文件」即可。

其余通用前提:想**白盒、可归因**地优化(看「为什么改这里、哪几题涨了、lineage 是什么」),且要**长期、可中断续跑**的优化过程。

不适合 / 注意:**没有可调产物的系统**(只有几个标量参数 → 用黑盒调参)、**评估不可重复 / 极昂贵**、**严格合规输出**(proposer 在沙箱里改文件——沙箱权限请自行审计)、**Proposer 必须是 LLM coding agent**(可调产物的进化需要 coding 能力;但被优化系统是否含 LLM 无所谓)。
