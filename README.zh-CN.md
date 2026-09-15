# AntOmniEvo

> [English](./README.md) · **中文**

**AntOmniEvo 是一个自动优化框架,分工明确:你定义系统的 editable parts 和「什么是好」—— framework 控制循环,AI 干活 —— 最终把优化后的 spec 交付给你。**

你系统中「可编辑的部分」被抽象为一份 **spec** —— 一个真实文件目录:agent 的 `SKILL.md` + 参考资料 + 脚本、workflow 的 `pipeline.json` + 节点脚本、单文件算法 + 它的描述。凡是能这么表示、又能被重复评估的系统,AntOmniEvo 都能优化 —— 优化变成了普通的文件编辑。被优化的系统不需要包含 LLM;但做优化的必须是一个 coding agent。

## 分工:你定义,framework 控制,AI 干活

**你定义** —— 五样东西,一次给出:

| 你提供 | 作用 |
|---|---|
| `System` | 如何**运行**你的系统(单条评估样本) |
| `Evaluator` | 如何给输出**打分**(0–1)—— 它的打分标准**就是**优化目标 |
| 评估**数据** | 定义「好」的训练 / 验证样本 |
| `SpecSchema` | 把系统的 editable parts 映射成一个文件目录:文件树 + 每个文件的用途 |
| **初始 spec** | 起点 |

**framework 控制** —— 它驱动 evolution loop,以及循环内所有的控制和工程工作:调度、预算、选择 / 淘汰、持久化 —— 都是你不用写的确定性机制,让种群中最强的候选存活;所有候选、运行、分析、changelog 全部落盘到 `CandidateStore`,可中断续跑。

**AI 干活** —— 真正动手改的是 coding agent 扮演的 `Proposer`:读失败轨迹、定位该改哪个 spec 文件、把一次结构化的变更落成一个新候选的 spec —— 像人改代码一样。

**它交付** —— 最优候选的 **spec**:一个真实文件目录,可以 diff、review、直接部署;附带变更 lineage,每一处改动都能归因到促成它的失败证据。

---

## 文档

| 主题 | 中文 | English |
|---|---|---|
| 安装与快速开始 | [docs/quickstart.zh-CN.md](./docs/quickstart.zh-CN.md) | [docs/quickstart.md](./docs/quickstart.md) |
| 系统特点 | [docs/features.zh-CN.md](./docs/features.zh-CN.md) | [docs/features.md](./docs/features.md) |
| 可扩展性 | [docs/extensibility.zh-CN.md](./docs/extensibility.zh-CN.md) | [docs/extensibility.md](./docs/extensibility.md) |
| 适合什么场景 | [docs/when-to-use.zh-CN.md](./docs/when-to-use.zh-CN.md) | [docs/when-to-use.md](./docs/when-to-use.md) |
| 系统设计 | [docs/system-design.zh-CN.md](./docs/system-design.zh-CN.md) | [docs/system-design.md](./docs/system-design.md) |
| workspace 产物与归因 | [docs/workspace-artifacts.zh-CN.md](./docs/workspace-artifacts.zh-CN.md) | [docs/workspace-artifacts.md](./docs/workspace-artifacts.md) |
| 断点续跑与崩溃恢复 | [docs/checkpoint-resume.zh-CN.md](./docs/checkpoint-resume.zh-CN.md) | [docs/checkpoint-resume.md](./docs/checkpoint-resume.md) |
| 可视化器 | [docs/visualizer.zh-CN.md](./docs/visualizer.zh-CN.md) | [docs/visualizer.md](./docs/visualizer.md) |

## 许可

基于 [Apache License 2.0](./LICENSE) 开源。法律免责声明见 [`LEGAL.md`](./LEGAL.md)。
