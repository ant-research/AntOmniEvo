# AntOmniEvo Skills

> [English](./README.md) · **中文**

按场景沉淀的 [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills),用于驱动
[AntOmniEvo](../antomnievo) 优化实验。每个 skill 把一个场景的最佳实践蒸馏成 agent 能直接执行的东西,
让下一个人跳过第一个人花了好几天才发现的坑。

**语言约定:本目录面向蚂蚁集团内部用户 —— skill 正文(`SKILL.md`、`references/`)用中文书写
(内部偏好);本 README 提供中英双语。**

## 为什么存在:agent 驱动,而不是人驱动

过去搭起一个 AntOmniEvo 运行的方式:人读框架文档、搞清楚需要哪些可插拔组件、手写入口脚本、
拍脑袋定并发 / 预算 / 环境变量,跑一次,然后调试每个人第一次都会踩中的失败模式。
整条学习曲线和每一个暗坑都由人扛着。

这个目录里的每个 skill 都要把这件事反过来:**skill 是一个主动驱动**实验搭建与管理的 agent。
它不会等你一步步下指令 —— 它会先问你几个只有你知道的事实(repo 在哪、数据集在哪、指标是什么),
然后接管剩下的一切:选组件、写入口脚本、设好合理默认值、启动运行,并通过把症状映射到
references 里记录的已知原因来分诊失败。

一句话:用户回答几个问题;接线、运行、避坑这些过去要人手工做的事,交给 agent。

## Skills

### eddy-antomnievo-experiment

**专为 eddy high-code agent runtime 打造。** 这个 skill 的存在,是为了让在 eddy 业务 agent 上
搭建 AntOmniEvo 优化实验成为一条固定、可重复的路径 —— 它的步骤、配方和踩坑记录都是针对
eddy 特有机制(entry 发现、轨迹 schema、沙箱传输、MCP 身份)写就的。
**其他 runtime 可以拿它当参考模板来蒸馏自己的 skill,但不能直接使用。**

用于把**蚂蚁内部 high-code agent runtime(eddy)的业务 agent** 接入 AntOmniEvo —— 你有一个
eddy agent,想让 AntOmniEvo 进化你选定的可调产物(prompt、skill、配置)。覆盖从 workspace /
数据搭建,到 `generate.py` / `evaluate.py` 冒烟,再到接好 System / Evaluator / Optimizer
循环的完整路径。蒸馏自 module-peizhiagent 项目的真实落地;每一步的细节和踩坑记录都在它的
`references/` 里。

## 建议

如果你在自己的 agent 场景上跑优化实验:照 `eddy-antomnievo-experiment` 的样子,把你辛苦趟出来的
最佳实践蒸馏成自己的 skill。一旦沉淀下来,实验搭建就由这个 skill 替你驱动 —— 不用重复手工接线,
也不会再踩你已经爬出来过的坑。
