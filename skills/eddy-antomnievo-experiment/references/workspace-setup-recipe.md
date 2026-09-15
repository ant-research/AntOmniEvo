# workspace 准备配方(AntOmniEvo 实验)

被 SKILL.md「步骤 1」引用:动手前先备好 AntOmniEvo 实验的落地基础。参照 `antomnievo/README.md` §5。

## 0. 两个目录概念(先分清)

"workspace" 拆成两个**不同**概念(详见 SKILL.md『两个目录概念』):

- **实验根目录(`<exp_root>`)**:整个实验的**非候选**产物 —— **本实验组件目录(`<exp_root>/antomnievo/`,默认;不是源码 clone —— AntOmniEvo 一律 pip 装包,这里放本实验补充的组件 + 入口脚本 + 最小 pyproject;venv 也在里面:`<exp_root>/antomnievo/.venv/`,是 AntOmniEvo 的专用环境)**、`NOTES.md`、config YAML、`run.env`、`tests/`、`initial_spec/`。**每实验自包含**(组件目录 + venv 都在 exp_root 内,不共享外部 venv);一个实验一个,跨多次 run 复用。
- **candidate store 根目录(`<candidate_store_root>`)**:**单独一个目录,只放优化 run 的候选数据**;里边每次 run 一个时间戳子目录 `<run_dir> = <candidate_store_root>/run_YYYYMMDD_HHMMSS/`(= `LocalCandidateStore(workspace_dir=<run_dir>)` 的落盘路径)。**resume = 同一个 `<run_dir>`;新 run = 新时间戳子目录。**

## 1. 让用户定两个路径

主动问用户(都要绝对路径、独立、可写、不和业务项目混),确认再往下。**问法:给候选 + 允许自输,别开放式问** —— 给 2~3 个**具体候选路径**让用户挑,也允许用户自己输入;候选按当前环境推断(如 `<cwd>/exp-<agent>`、`<work_root>/exp-<agent>`),每个候选附一句取舍说明;用户确认前不动手:

- **`<exp_root>`** 放哪;
- **`<candidate_store_root>`** 放哪(候选给:默认 `<exp_root>/workspace`(**推荐**)、`<exp_root>/candidate_store/`、独立路径(候选数据 = spec 树 × 候选 × 代,体积可能很大,想放别的盘就独立路径,用户自输))。

```
<exp_root>/                      # 实验根目录(步骤 1 创建)
  antomnievo/                      # 本实验组件目录(非源码 clone;本实验补充的组件/脚本都放这)
    .venv/                       # AntOmniEvo 专用 python 环境(python ≥ 3.12;pip install ant-omnievo)
    pyproject.toml               # 最小打包,让 <scenario>/ 场景包可 import(uv pip install -e .)
    <scenario>/                  # 本场景组件包(如 peizhiagent/)
      dataset/  spec_defs/  system/  evaluator/  optimizer/  scripts/  <domain>_optimize.py
  NOTES.md                       # 实验记忆(每步追加)
  opt_config.yaml                # config YAML(步骤 10 写;secrets 在这)
  run.env                        # 入口从 YAML 物化(步骤 10)
  initial_spec/                  # 抽出的 initial spec(步骤 9/10)
  tests/<smoke_name>/            # 冒烟/测试产物(保留不清)
  examples/                      # (可选)从 antomnievo/example/ 拷来的入口脚本、改写的 entry-point

<candidate_store_root>/          # candidate store 根目录(单独目录;步骤 1 只建根,不建 run 子目录)
  run_YYYYMMDD_HHMMSS/           # <run_dir>:每次优化 run 一个时间戳子目录(步骤 10 optimize() 时才建)
    candidates/<candidate id>/   #   各 candidate:spec 树 / meta / changelog / best / run 产物
    logs/statistics.json         #   优化统计(resume 判定:有无 root_candidate_id)
```

> candidate store 输出 = `LocalCandidateStore(workspace_dir=<run_dir>, cleanup_unavailable=False)`;config YAML 里 `<run_dir>` 的 key 叫 `workspace_dir`(与参数同名)—— 它指 candidate store 的单次 run 目录,不是 `<exp_root>`。

## 2. 建组件目录 + 专用 python 环境 + pip 装 AntOmniEvo(不拉源码)

路径定了后,**建 `<exp_root>/antomnievo/`(本实验组件目录,非源码 clone)**,并在其中**创建一个专供 AntOmniEvo 使用的 python 环境**(`<exp_root>/antomnievo/.venv/`,python ≥ 3.12):

```bash
# 建组件目录(本实验补充的 dataset/spec_def/System/Evaluator/Optimizer/入口脚本都放这)
mkdir -p <exp_root>/antomnievo

# 在其中建 AntOmniEvo 专用 venv(python ≥ 3.12)
uv venv --python 3.12 <exp_root>/antomnievo/.venv

# pip 装 AntOmniEvo(不拉源码 clone;core 依赖 pydantic ≥2/httpx/tenacity/pyyaml 跟着进)
uv pip install ant-omnievo --python <exp_root>/antomnievo/.venv/bin/python

# 问用户要不要可视化前端:要 → 装 visualizer 包(README §9;前端 React 还要 npm install)
uv pip install ant-omnievo-visualizer --python <exp_root>/antomnievo/.venv/bin/python

# 组件目录放最小 pyproject + editable 装进同一 venv → 场景包可 import(PYTHONPATH 兜底)
uv pip install -e <exp_root>/antomnievo --python <exp_root>/antomnievo/.venv/bin/python
```

组件目录的最小 `pyproject.toml`(`<scenario>` 换成本场景包名,如 `peizhiagent`):

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "antomnievo-exp-components"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
include = ["<scenario>*"]
```

> **业务项目自己的运行/打分 harness 不在这里装**:README §5 明确——your `System`/`Evaluator` 若 shell out 到自己的运行/打分,各自单独装;AntOmniEvo 不管。本 skill 的 `generate.py`/`evaluate.py` 跑在**业务项目自己的 venv**,不是这个 AntOmniEvo venv。

> **proposer 的 coding-agent CLI 也分开装**(步骤 10 启动 proposer 才需要):
> - agent proposer **固定默认用 pi 实现**(`antomnievo/proposer/` 里 pi-based 的 `BaseProposer` 实现;**不给用户选 claude 实现 —— claude 目前有问题**):先 `which pi && pi --version` 检查;**没装 → `npm install -g @mariozechner/pi-coding-agent`**(需 **Node ≥ v22.22.1**;没 Node → `brew install node` 或 `nvm install 22.22.1`)。`pi` 启动可能要登录 / 设模型网关 key(按 CLI 提示),提前跑 `pi --help` 看格式;proposer YAML 里的 `api_key`/`base_url` 是喂给 `pi` 的 LLM 网关。

## 3. 读 README + 选 example(从已装包里读,不 clone)

- 先定位已装包:`<pkg> = $(<exp_root>/antomnievo/.venv/bin/python -c "import antomnievo,os;print(os.path.dirname(antomnievo.__file__))")`。
- 读 README(随包装在 `<pkg>/../README*.md`;没有就 `pip download` 或让用户给仓库地址只读参考),重点 §5/§6/§7/§8。
- `<pkg>/example/` 是**参考实现**(每份是一个不同系统形态的入口接线):挑最像的一份当起点。
  - `example/rag/agentic_rag_internal.py` —— 最简单端到端(in-process system + 基础 `Optimizer`)。
  - `example/text2sql/birdtest_text2sql.py` —— batch-subprocess `System` + 场景 `Optimizer` 子类(更接近"调业务项目脚本"的形态,**本 skill 的 gen/eval 主要对标这种**)。
  - 另:`example/terminalbench/`、`example/appworld/` 也可参。

## 4. entry-point 形态(不在此复制)

去读 AntOmniEvo 的 example(见上 §3)即可,按你选中的那份 entry-point 改;**本 recipe 不重复贴骨架**,以免和上游 example 跑偏。

## 5. sanity check(写完即自测)

```bash
<exp_root>/antomnievo/.venv/bin/python -c "import antomnievo; print(antomnievo.__file__)"   # 应指向该 venv 的 site-packages(证明用的 pip 包)
<exp_root>/antomnievo/.venv/bin/python -c "from antomnievo.store.candidate_store import LocalCandidateStore; print(LocalCandidateStore)"
```
能 import `antomnievo` + `LocalCandidateStore` 即环境 OK。

> 注:`System` / `Evaluator` / 4 个组件的接线和 `await optimizer.optimize()` 属于 AntOmniEvo **后续步骤**(System 跑你写的 generate、Evaluator 调你写的 evaluate),不在本 skill(本 skill 只到 data + gen/eval + 冒烟确认)。本 recipe 只把 workspace/venv/README 备齐,让你写后续模块时有据可依。
