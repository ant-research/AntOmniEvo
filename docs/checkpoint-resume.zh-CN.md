# 断点续跑与崩溃恢复

> [English](./checkpoint-resume.md) · **中文**

AntOmniEvo 设计上随时可中断、随时可续跑:

- **同 `workspace_dir` 重启**:启动时检查 `statistics.root_candidate_id`,存在 → 续跑(跳过 root baseline),不存在 → 从头建。
- **崩溃时处于 `evolving` 的候选**:`__init__` 末尾调 `reset_evolving_to_pending()` 全部翻回 `pending`。
- **残留 `unavailable` 候选**:若 `cleanup_unavailable=True`,启动时清掉。
- **产物落盘可靠**:run record / analysis / changelog / trajectory 都是 append 或原子写;即使 LLM 在 mutation 中途报错,也会先落盘 trajectory 再报错。

**实操**:续跑就用同一入口脚本、同一 `workspace_dir`。重新跑就换一个带时间戳的 `workspace_dir`。这是唯一要注意的点。
