# 系统特点

> [English](./features.md) · **中文**

## 1. 优化对象:spec 即基因组

- 被优化的**不是**受限参数集或受限 DSL,而是**一目录真实文件**;变异 = coding agent 在其中增 / 删 / 改文件。
- **不限于 Agent**:凡「可编辑文件目录 + 可重复评估」的系统都是合法优化对象——AI Agent 的 skill/harness/memory、workflow 的 `pipeline.json` + 节点脚本、单文件算法(`.py`/`.ts` + spec 描述)。被优化对象是否含 LLM 不影响框架,`System` 接口只要求「吃了 spec + 数据、吐 trajectory + 输出」。
- 每个改动结构化为 `SpecAction{file, operation, spec_issue, change, resolves[]}`,必须回指它要修复的某个失败轨迹观察,这让变异**可追溯、可消解矛盾、可质量门控**。
- 表达力 = 文件系统能装下的一切:改一段 Markdown 规则、改一段 Python 实现、加一个校验脚本、加一个运行时 extension 硬约束…… 都行,不限预设字段。

## 2. 进化算法:并发 + Mara 链 + micro-pareto

- **多 slot 并发进化**:最多 `num_proposals` 个候选**同时**各占一个进化 slot,共享候选池 + 候选状态机;前作(GEPA / ACE / AHE)是串行进化。
- **Mara 链深度修复**:单 batch 未达标时不止于一次自然语言反思,而是把失败链的逐题分数历史、归属化 changelog、既有分析**预加载进 prompt**,强制走五法诊断(因果溯源 / 成功提取 / 振荡检测 / 不一致发现 / 证据印证)产出下一轮候选,最多 `max_reflection_iterations` 轮,取链中最佳且超越原始 parent 者接受。
- **Micro-pareto 选择**:逐数据实例的 Pareto 弱支配剪枝 + top-N 截断兜底;select 时用「多维度领先次数」加权采样,保护多面手候选。(注:Pareto 选择本身沿用 GEPA,不是 AntOmniEvo 增量;AntOmniEvo 算法增量在**并发**与**Mara 链**。)

## 3. 工程基建:记忆、隔离、可观测、可插拔

- **两阶段 proposer(分析 → 变异)**:Phase 1 把失败运行蒸馏成结构化 `RunAnalysis`(原始 run 不直接喂变异器);Phase 2 跨数据实例去重 / 消解矛盾后落盘。独立质量门 `validate-analysis`(自检)+ 强制走 `append-changelog`(lineage 可追溯)。
- **文件系统即记忆 + 断点续跑**:append-only `changelog.jsonl`、child 继承 parent 副本;候选状态机 + 启动 `reset_evolving_to_pending`,任意时刻中断重启都能续跑。
- **多维度预算控制**:`Budget` 四个正交硬上限(`max_iterations` slot 数 / `max_rollouts` 总 rollout 数 / `max_tokens` 累计 token / `max_elapsed_seconds` 墙钟),任一 `None` = 该轴不限,任一达上限即停止开新 slot、在飞 slot 排空后再退出(软停止 + Drain 语义,配合断点续跑长跑不超支)。
- **可接云端存储**:`CandidateStore` 是抽象 ABC,默认 `LocalCandidateStore` 把进化记忆落本地 `workspace/`。接云端基建时实现一个「本地 + 透明同步」的子类:对优化器完全透明,内部仍本地跑,每次落盘同时把产物(spec 树、meta、changelog、best 候选)同步到对象存储 / DB,演化前从云上拉初始 spec、演化后产物供下游消费。主循环与单进程多 slot 并发逻辑不变。
- **验证集硬隔离**:`val_system_run/` 对 proposer 是禁区(Pi 路线附加运行时 extension 硬拦截),proposer 看不到任何验证集轨迹;训练 batch 决定「变异是否值得保留」,验证集决定「候选在种群里的位置」,杜绝 spec 过拟合 val。
- **自带可视化器**:React + Flask 前端,从一个 workspace 目录渲染整个进化过程。
