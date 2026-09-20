# AntOmniEvo Example 入口脚本编写配方(步骤 10)

对应 AntOmniEvo 的**入口脚本**:把 System + Evaluator + Optimizer + Proposer + EA +
CandidateStore 装起来、跑 `await optimizer.optimize()`。**所有配置(含 secrets)
放一个 workspace YAML 文件,入口加载,绝不硬编码 secrets。**(本配方是对标
`antomnievo/example/text2sql/birdtest_text2sql.py`;但 text2sql 把 secrets 读 env + 写
码里,本配方要求集中到 workspace YAML。)

---

## §0 放哪
入口脚本:`<exp_root>/antomnievo/<scenario>/<domain>_optimize.py`(组件目录的场景包,统一约定;参照结构读已装包里的 `antomnievo/example/text2sql/`)。
配置 YAML(含 secrets):**`<exp_root>` 下**,一个专门文件(如 `<exp_root>/opt_config.yaml`),入口 `--config` 加载。**别**放业务仓库 / 别提交。

---

## §1 先读
- 入口范本 `antomnievo/example/text2sql/birdtest_text2sql.py`(wire System+Evaluator+Proposer+EA+CandidateStore+Optimizer + `optimize()`,怎么 `import`/构造/`config.yaml` 加载)。
- 你的 System(步骤 7)/Evaluator(步骤 8)/Optimizer 子类(步骤 9)的**构造参数** —— 入口要用;kwarg 签名已在 7/8/9 对齐。
- agent proposer(抽象名;`antomnievo/proposer/` 里 `BaseProposer` 的具体实现,以已装包实际为准、不写死实现名)构造(tunable_artifact_schema/candidate_store/evaluator/system/api_key/base_url/model/provider/... 以所选实现签名) → 你要的 proposer 配置(YAML `proposer.*` + tunable_artifact_def)。
- `ParetoFrontierEvolutionAlgorithm`/`Budget`/`LocalCandidateStore` 构造。
- **tunable_artifact_def**(步骤 3 或本步写,`<exp_root>/antomnievo/<scenario>/tunable_artifact_defs/<domain>_tunable_artifact_def.py`)→ 喂给 proposer。
- 看 `Optimizer.optimize()` 主循环背的依赖 → 确认你入口备全(train/val/budget/initial_artifacts_dir)。

---

## §2 怎么写

### 主动问用户要配置(别硬编码)
入口要的 secrets/config **让用户提供**,你**主动问**(不猜):
1. **proposer**:`api_key` + `base_url`(+ `model`/`provider` 等,以所选实现签名,可问默认)。**proposer 固定用 pi 实现**(不让用户选 claude —— claude 目前有问题):**先确认 `pi` CLI 装了**(`which pi`,没装 → `npm install -g @mariozechner/pi-coding-agent`,需 Node ≥ v22.22.1,装完 `pi --version` 确认)。
2. **system**(agent/mcp 跑要的,看项目主进程读的 env 名):模型 key(本项目 `THETA_API_KEY`)+ MCP 身份 token(本项目 `IAM_TOKEN`)。
3. 路径(repo/源码仓库/cases/schema_manifest)+ workspace_dir + `initial_artifacts_dir`/`tunable`。超参不问用户,先用默认(batch_size/num_proposals 用 Optimizer 默认);预算跟用户讲清支持的类型(`max_iterations`/`max_rollouts`/`max_system_runs`/`max_tokens`/`max_elapsed_seconds`),**默认时间预算 8 小时**(`max_elapsed_seconds: 28800`),并告诉用户调参位置 = config YAML 的 `hyperparams` 段。
用户告诉你 → 你写 YAML;或用户直接给文件你接。收齐后**自查缺不缺**(入口 `--check-config` 列缺失),少了让用户补,最终加载进 YAML。

### ⚠ workspace_dir:实验目录(不是单一 workspace,是一个父目录下的 timestamped 子目录)

`workspace_dir` 在 YAML 里指向 **一个带时间戳的实验子目录**(不是父目录)。AntOmniEvo 的 `LocalCandidateStore` 初始化时:目录不存在 → 新建(fresh);已存在且有 `statistics.json`+`root_candidate_id` → **自动续跑**(resume)。

```
opt_workspace/                         ← 父目录(放很多次不同实验)
  run_20260829_200011/                 ← 实验 1(timestamped)
    candidates/                         ← candidate store
    logs/                                ← optimizer 日志
    statistics.json                      ← Optimizer 统计(有 root_candidate_id → resume)
    run.env                              ← 物化的 THETA/IAM
    optim_*.log                          ← 运行日志
  run_20260901_120000/                 ← 实验 2(timestamped,新的)
    ...
```

YAML:
```yaml
workspace_dir: /Users/jacklv/<repo>/opt_workspace/run_20260829_200011   # ← 指向 timestamped 实验子目录
```

- **续跑同个实验**:用**同一** `workspace_dir`(同一个 timestamped 子目录路径)。AntOmniEvo 检查 `statistics.root_candidate_id`(README §8:存在 → 续跑跳 root baseline;不存在 → 从头建)。
- **开新实验**:换成**新** timestamped 子目录(`run_<新时间戳>/`)。老实验的目录留着不动。
- **不需要 flag**:resume 是 AntOmniEvo 的内置行为 —— `workspace_dir` 有数据就 resume,没数据就新建。**唯一要注意的就是路径**(README §8 原文:"续跑就用同一入口脚本、同一 workspace_dir。重新跑就换一个带时间戳的 workspace_dir。")。

⚠ `initial_artifacts_dir` ≠ `--agent-src`(agent module)!`initial_artifacts_dir` 是用脚本从 agent module **只抽出可调部分**生成的干净 artifact 目录:
```bash
# scripts/extract_initial_artifacts.py — 抽取可调产物
python scripts/extract_initial_artifacts.py \
  --agent-src src/<pkg> \  # agent module 包根
  --tunable <entry1> \   # 步骤 3 对齐的可调条目(e.g. agents),可重复
  --output <workspace>/initial_artifacts  # 输出
```
- **为什么**:LocalCandidateStore `create_root` 整树 `copytree`(只 ignore `__pycache__`)→ 把 `initial_artifacts_dir` 整份拷进每个候 → 跑代留下基线快照。如果你把 `initial_artifacts_dir` 设成整个 agent module,会把 config/ + knowledge_data/*.jsonl(重数据)+ main.py/app.py(平台 bootstrap)也拷进每个候选 → ① 重数据 × 候选 × rollout = 存储爆炸、② proposer 能碰非可调(破坏平台 bootstrap / 运行配置)。
- **可调产物 ≠ agent module**:可调产物只是你跟用户对齐的**可调行为面**(步骤 3 — 如本项目的 `agents/` 子包);agent module 还包含**不可调**的 config/、knowledge_data/、main.py/app.py/solution.py(在 generate.py 的 `--agent-src` 里用,运行时代理包)。可调产物放 `initial_artifacts`,agent module 在 `--agent-src`,generate.py `--tunable <ent>` 把候选的可调 `<ent>` overlay 回运行期包跑(见步骤 4 load 可调产物)。
- **脚本放 `scripts/extract_initial_artifacts.py`**(业务仓库);`--tunable` 用步骤 3 跟用户对齐的列表(e.g. `agents`);若用 `agents`+另一 `--tunable <another>`,脚本会拷两份,放进 `initial_artifacts/<ent>` 各自 pkg-rel path 位置。
- 跑完脚本把 `<workspace>/initial_artifacts` 写进 YAML 的 `initial_artifacts_dir:` 即可;**`initial_artifacts_dir` 不能设成 `--agent-src`/`src/<pkg>`**。
```yaml
# <workspace>/config.yaml — secrets do NOT commit.
workspace_dir: <workspace>
repo: <业务仓库>; local_source_repo: <项目源码仓库>
cases: <cases jsonl>; schema_manifest: <prebuilt manifest>
agent_src: <repo>/src/<pkg>; initial_artifacts_dir: <同左>; tunable: ["<可调根>"]
system:  # entry 从这两条物化 <workspace>/run.env 给 generate.py --env-file
  python: <repo>/.venv/bin/python
  generate_script: <repo>/scripts/generate.py; evaluate_script: <repo>/scripts/evaluate.py
  theta_api_key: "..."   # REQUIRED (model key)
  iam_token: "..."       # REQUIRED (MCP 身份; 无 MCP 可省)
  timeout: 1200; concurrency: 1;  # + 项目特定 flag(看 evaluate.py --help + 跟用户对齐)
proposer:
  api_key: "..."         # REQUIRED (coding-agent key)
  base_url: "..."; model: kimi-k2.5; pi_path: pi; provider: anthropic
  max_turns: 150; timeout: 3600; concurrency: 2
hyperparams: {train_max, val_max, batch_size, max_iterations, num_proposals, max_reflection_iterations, min_improvement_per_batch}
budget:
  max_iterations: 1000        # 迭代上限(必填,或用 hyperparams.max_iterations = 实际写法)
  max_tokens: 5000000         # LLM token 累计上限(安全网;None=不限,但建议设)
  max_elapsed_seconds: 86400  # 一天(安全网;None=不限,但建议设)
evolution: {max_candidate_num: 3}
```
必填 secrets(入口 `--check-config` 校验):`system.theta_api_key`、`system.iam_token`(用 MCP 时)、`proposer.api_key`、`proposer.base_url`、`proposer.model`(**model 没有默认值,用户必须认真填**)。

⚠ **`proposer.model` 不是可选的** —— 之前用了 `prop.get("model", "kimi-k2.5")` 给默认值,但你换了 LLM 网关(antchat / GLM)就填错 model 名 → 要么连不上,要么用错模型。现在 `--check-config` 必查它:缺了报 `missing required: ['proposer.model']` → 用户必须填(在 YAML 的 `proposer.model:` 里写真实 model 名,如 `GLM-5.2`)。

### 入口脚本(`<exp_root>/antomnievo/<scenario>/<domain>_optimize.py`)
`argparse --config`(或 env `<DOMAIN>_CONFIG`/默认 `./config.yaml`)+ `--check-config`(只校验、不跑)→ `yaml.safe_load` → 校验必填 secrets → **物化 `<workspace>/run.env`**(从 `system.theta_api_key`/`iam_token` 写 `THETA_API_KEY`/`IAM_TOKEN=` 两行)→ 构造 `System(env_file=run.env)` + Evaluator + agent proposer(`BaseProposer` 具体实现以已装包为准;`tunable_artifact_schema=<tunable_artifact_def>, ..., api_key/ base_url/ model/... = YAML`) + `ParetoFrontierEvolutionAlgorithm` + `LocalCandidateStore(workspace_dir)` + `<Domain>Optimizer(..., initial_artifacts_dir=...)` → `len(train)=train_max`/`val` 顺序子集切 → `await optimizer.optimize()`。**绝不**在代码里 `api_key="..."`。

---

## §3 坑
1. **别把 secrets 写进代码** —— 放 workspace YAML(`--config`),入口加载;别提交 YAML。
2. 配置**主动问用户**、收齐 `--check-config` 查缺(必填缺就停,让用户补)。
3. **`run.env` 由入口从 YAML `system.*` 物化**(generate.py `--env-file` 读),**单源 = YAML**(别同时硬填 `.env.local`,否则两源打架)。
4. **proposer 需 `pi` coding-agent CLI**(装好)+ proposer key;全量 `optimize()` 还要 model key + MCP 权限 + sandbox 仓库 + schema manifest + 大开销(每候选真跑 agent + LLM 改可调产物),**别误跑**;先 `--check-config` 再小 budget。
5. **数据集对齐**(train/val 哪来 / 本地 / 云端 / 格式跟步骤 2 对齐 / val 可能空) —— **主动跟用户对齐** THEN 在 YAML `hyperparams` 里写 **真跑数量**(`train_max`=用户对齐的数(如 98);`val_max` 默认 0 = 空 val)。`cases`(gold 文件路径)。⚠ **不要在代码里给 `val_max` 非 0 默认**(我之前默认 2,矛盾,已改 0)。

    ⚠ **冒烟数据量别改 hyperparams——用 `smoke: true` 开关 override**:
    - YAML 顶层加 `smoke: true` → 代码 override 到 `train_max=2, val_max=0, max_iterations=1, num_proposals=1, batch_size=1`(**快速冒烟**,不改 hyperparams)。
    - 冒烟完 → YAML 改 `smoke: false` → 用 hyperparams 里的真跑数量(**自动恢复**到对齐的量)。
    - **为什么不改 hyperparams 冒烟**:改了数字冒烟完要手动恢复,容易忘 → 我之前就写成 train=2 忘了恢复。开关隔离了冒烟 vs 真跑 ——hyperparams 永远是对齐的真跑数量,smoke 只是把数据量临时 override 小。
6. 路径全绝对(通用约定)、测试 workspace 没 → `/tmp`(通用约定)。
7. `system_description`(步骤 7)/`scoring_criteria`(步骤 8)已写好 → proposer 用,错或空→错误归因(通用约定)。

---

## §4 怎么验证
1. **`--check-config`**:列必填 secrets 缺不缺(没少才跑);列出缺的 optional 字段(会回退默认)。
2. **小 budget `optimize()`**(可能/重):`max_iterations=1`、`train≈2`、`val≈1`、`num_proposals=1` 跑一次 —— 看根 baseline → proposer 改可调产物 → 子候选 跑+评 → 比较/淘汰 循环通(proposer CLI + 全前置就绪后)。
3. 再放大 budget,关注 Pareto/采纳数 + token/时间预算。

### ⚠ `eval_stage`(全量 vs 快档)—— 选择 + 持久化路径

- `eval_stage` 是**你的 evaluate.py 接受的 stage flag** —— 看项目 `--help`，跟用户讨论用哪个 (e.g. fast "deterministic" vs full "all" 是一个项目对 evaluate.py 可能的两种调用形态，但具体名字 + 跑什么 + 产出什么是项目-specific 的)。**Skill 不预设 stage 名 / 跑什么 stage 内容 / 产出什么文件** —— 看 `scripts/evaluate.py --help` + 跟用户确认。
- **从 fast → full 的通用 trade-off**:fast(e.g. 一档)是走快路径快速给 optimizer 信号;detailed(e.g. full + LLM judge + runtime)慢(~分钟/case vs ~秒/case)；**在 optimizer loop 跑 detailed 档，每候选 evaluation 变慢 → optimizer 迭代慢** → 跟用户讨论你需要 fast 还是 detailed 作为 optimizer 的 metric 而不是 skill 预设。
- ⚠ **optimizer 的 `_run_and_evaluate` 把 gen + eval 产物持久化到 workspace**(`workspace/<candidate_id>/<batch_label>_<timestamp>/{generate,evaluate}/`，不用 tempfile)，evaluate 产物不删 —— 这样用户在 workspace 里就能看 evaluate.py 写出的完整 multi-stage 报告 (per-case details / report / 各 stage 中间产出)，不用再跑一遍。LLM judge 等中产物都跟着 persist;**这是通用方法论，不是 skill 决定跑哪 stage**。

### ⚠ val=0 时怎么看结果(关键)
当 `val_max=0`(val 空):
- **`summary.json` 的 `avg_score` 始终 0**(无 val → `_step_validate` 跑空 → `0/0 fallback = 0`),**不能用 avg_score 判断"优化了没"**。
- **看优化器日志里每个 iteration 的 batch 对比**:
  ```
  Parent <id> scores: [case_id=0.6, ...], Child <id> scores: [case_id=0.8, ...]
  New candidate <id> ... (new=2.4, old=1.8, threshold=0.5), accepting / rejecting
  ```
  - `old` = parent 在 train batch 的分数和 → `new` = child 在同 batch 的分数和 → `improvement = new - old`。
  - `improvement >= threshold` → 采纳(child 确实 iterative 变好了)→ 进入下一 iteration。
  - `improvement < threshold` → 拒绝 → EA 选下一候选再试。
- **per-iteration 的 batch improvement 才是 val=0 时的优化信号**:每一轮 `old → new → improvement` 是你要看的东西;不是 summary.json.avg_score(那是 val 的,空=0)。
- 这就是你为什么要跟用户对齐 "train 用多少数据" —— train batch 上的分数提升 = 你的优化效果度量;val=0 时,优化循环仍然可以通过 train batch improvement 接纳更优候选。

---

## §5 ad-config 实例代码位置(请直接读代码,不在此拆业务细节)
- 入口: `antomnievo/example/adconfig/adconfig_optimize.py`
- tunable_artifact_def: `antomnievo/model/tunable_artifact_defs/adconfig_tunable_artifact_def.py`
- 初始可调产物抽取: `scripts/extract_initial_artifacts.py`
