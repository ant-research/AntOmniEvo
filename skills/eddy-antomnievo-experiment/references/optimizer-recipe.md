# AntOmniEvo Optimizer 子类编写配方(步骤 9)

对应 AntOmniEvo 优化循环里的 **Optimizer 子类**:override `Optimizer._run_and_evaluate`,把 System.run_batch + Evaluator.evaluate_batch 经 kwargs 串起来、每候选一个 tempdir 跑+评。(入口脚本 + tunable_artifact_def + config 是步骤 10,见 `entry-recipe.md`。)

---

## §0 放哪 + 用默认还是扩展?(关键决策,看 generate/evaluate 的输入输出)

**放哪**:组件目录(同步骤 7,统一约定)—— optimizer 子类 → `<exp_root>/antomnievo/<scenario>/optimizer/<domain>_optimizer.py`,入口 → `<exp_root>/antomnievo/<scenario>/<domain>_optimize.py`。

**用默认还是扩展?** —— 看你(步骤 4)写的 generate.py / evaluate.py 的输入输出:
- **子进程 + 文件路径 I/O**:generate 取 `--cases`/`--output-dir`/`--artifact-dir`,evaluate 取 `--predictions`/`--cases`/`--output` —— 默认 `Optimizer._run_and_evaluate`(调 `system.run_batch(meta, data_list)` + `evaluator.evaluate_batch(data_list, results)` **不传任何 kwargs**,纯 in-process)给不出这些路径 → **必须 subclass + override `_run_and_evaluate`**(造 tempdir → 写 batch cases → thread `output_dir`/`cases_path`/`predictions_path`)。对标 `Text2SQLOptimizer`。
- **in-process**:System/Evaluator 拿 `data_inst` 直接出 `SystemResult`/`EvaluationResult`、无文件 I/O —— 默认 `Optimizer` 就够,**别 subclass**(用通用约定里说的现成 `Optimizer(...)`)。

本项目 generate/evaluate 都是子进程 → 要 subclass。**这个决策不是猜的,是看 generate/evaluate 实际要什么 I/O 得出的**。

---

## §1 先读:optimizer 契约 + 找最像的 example
1. `antomnievo/optimizer/optimizer.py` —— `Optimizer`:`_run_and_evaluate(candidate_id, data_list) -> RolloutEvalResult`(默认调 `run_batch(meta,data_list)` + `evaluate_batch(data_list, results)` 不传 kwargs);`optimize()` 主循环(选优 → proposer → 比 → 淘汰 → 验证 → persist run-record → Budget)。看清楚默认 `_run_and_evaluate` 跟 `optimize()` / `_run_and_evaluate_wrapper` / `_save_run_record_list` 的分工(你 override 的是 `_run_and_evaluate`,persist/计数在 wrapper 里)。
2. **最像的 example**(subclass 形态)→ `antomnievo/optimizer/text2sql/text2sql_optimizer.py`(`Text2SQLOptimizer._run_and_evaluate`:tempdir → 写 dataset_batch → `run_batch(output_dir, contexts_path)` → `evaluate_batch(output_dir, predicted_sql_path, contexts_path)`)。
3. `Optimizer.__init__`(constructor 要什么):`system`/`proposer`/`evaluator`/`evolution_algorithm`/`candidate_store`/`train_dataset`/`val_dataset`/`batch_size`/`budget`/`num_proposals`/`max_reflection_iterations`/`min_improvement_per_batch`/`initial_artifacts_dir`。
4. `ParetoFrontierEvolutionAlgorithm`(EA;`candidate_store`+`max_candidate_num`)、`Budget`(`max_iterations`/`max_rollouts`/...)、`LocalCandidateStore`(`workspace_dir`,`cleanup_unavailable`)、agent proposer(抽象名;`antomnievo/proposer/` 里 `BaseProposer` 的具体实现,以已装包实际为准、不写死实现名;`tunable_artifact_schema`/`candidate_store`/`evaluator`/`system`/`api_key`/`model`/... 以所选实现签名) —— 看构造参数。

---

## §2 怎么写(subclass + tunable_artifact_def + 入口)

### Optimizer 子类(override `_run_and_evaluate`)
```
async def _run_and_evaluate(self, candidate_id, data_list) -> RolloutEvalResult:
    meta = self.candidate_store.get_meta(candidate_id)
    with tempfile.TemporaryDirectory(prefix=f"<domain>_{candidate_id}_") as tmp:
        gen_dir = tmp/"generate"; eval_dir = tmp/"evaluate"; mkboth
        batch_path = tmp/"cases_batch.jsonl"
        write batch cases = sorted(data_list, by id) -> each data_inst.to_case_dict() 每行
        results = await self.system.run_batch(meta, data_list, output_dir=gen_dir, cases_path=batch_path)
        predictions_path = gen_dir/"predictions.jsonl"
        evals = await self.evaluator.evaluate_batch(data_list, results, output_dir=eval_dir,
                                                    predictions_path=predictions_path, cases_path=batch_path)
    return RolloutEvalResult(results=results, evals=evals)
```
- **kwarg 名要跟步骤 7/8 你写的 System/Evaluator 的 `run_batch`/`evaluate_batch` 签名对齐**(本例:`output_dir`/`cases_path`/`predictions_path`)。
- batch cases **全行带 gold**(`data_inst.to_case_dict()`)—— generate 读 app/env/base_version、evaluate 读 `expected.artifact.changes`。
- per-candidate per-batch 独立 tempdir(产物隔离)。

### tunable_artifact_def(`<exp_root>/antomnievo/<scenario>/tunable_artifact_defs/<domain>_tunable_artifact_def.py`)
`TunableArtifactSchema = FolderSchema(name=<步骤 3 约定的可调根>, description=<本场景 agent 行为 + 树>, files=[FileSchema/FolderSchema ...])` + **约束段**(无冗余/矛盾、跨实例泛化、改后仍 `python -c "import <入口>"` 通过、保工具流+HITL、别耦合单 case、别动非可调的 runtime/重数据)。proposer 靠它 mut 可调产物。可对号已装包里 `antomnievo/model/tunable_artifact_defs/text2sql_tunable_artifact_def.py` 的结构(别套业务字段)。

### 入口脚本(跑 `await optimizer.optimize()`)
装 System(步骤 7)+ Evaluator(步骤 8)+ agent proposer(抽象名;`BaseProposer` 具体实现以已装包为准,`tunable_artifact_schema=<tunable_artifact_def>, candidate_store, evaluator, system, api_key, ...`)+ Ea(`ParetoFrontierEvolutionAlgorithm`)+ `LocalCandidateStore(workspace_dir)`+ `<Domain>Optimizer(..., initial_artifacts_dir=<extracted artifact dir>)` → `await optimizer.optimize()`。train/val(无划分 → 顺序子集切先冒烟;正式分层按用户对齐)。对标 `antomnievo/example/text2sql/birdtest_text2sql.py`。

---

## §3 坑(实测得的)
1. **默认 Optimizer 不传 kwargs** → 子进程形态必须 subclass(决策见 §0,看 generate/evaluate I/O)。
2. batch cases **全行带 gold**(`to_case_dict`),否则 generate 读不到 app/env/base_version、evaluate 读不到 gold。
3. **kwargs 签名跟步骤 7/8 的 System/Evaluator 对齐**(`output_dir`/`cases_path`/`predictions_path`)—— 名字对不上就 TypeError。
4. per-candidate per-batch 独立 tempdir(产物隔离,别共用)。
5. `_run_and_evaluate` **自己不 persist run-record**(`_save_run_record_list` 在 `_run_and_evaluate_wrapper`/`_evolve_one` 里)—— 裸调它做 wiring 冒烟看不到 `run_*.json` 是正常的;要 persist 走 `optimize()` 或 `_run_and_evaluate_wrapper`。
6. **agent proposer 需要其对应的 coding-agent CLI + api_key**(要哪个 CLI 看所选实现的实现名/文档/报错);全量 `optimize()` 还要 model key + MCP 权限 + sandbox 仓库 + 预建 schema manifest —— 都是重开销(每候选 = 真跑 agent + LLM coding agent 改可调产物,多代多候选),**别误跑**(确定好再跑)。
7. train/val 划分 → 入口里切(无统一划分用顺序子集够冒烟;正式分层按用户对齐)。
8. 路径全绝对(通用约定);测试/`candidate_store` workspace 没 workspace → 放 `/tmp`(通用约定),正式跑用真 workspace。
9. `system_description`(步骤 7)/`scoring_criteria`(步骤 8)已写好 → proposer 会用,错或空会让它错误归因(通用约定)。

---

## §4 怎么验证(两层)
1. **wiring 冒烟(必做,不跑 proposer)**:构造 optimizer(proposer 用占位 `api_key`、**不调它**)+ `candidate_store.create_root(initial_artifacts_dir=<exp_root>/initial_artifacts)`(步骤 3 抽好的目录) → `await optimizer._run_and_evaluate(root_id, [1 case])` → `RolloutEvalResult`;断言:`results[0]` SystemResult `prediction_present=True`(+ artifact 字段)、`evals[0]` `EvaluationResult(score∈[0,1], reason)`、已知正确 case `score≥0.9`。验证 System↔Evaluator 经 optimizer 的 kwargs 串通 + 候选可调产物能 load(≈1 agent run)。没 workspace → candidate_store workspace + 输出放 `/tmp`。
2. **全量 `optimize()`(可选/重)**:入口跑 `await optimizer.optimize()`,需 proposer 对应 CLI + proposer api_key + 全前置。先**小 budget**(`max_iterations=1`、`train≈2`、`val≈1`)验证 root baseline → propose → child → 比较 循环通,再放大。轨迹/统计看 `<workspace>/NOTES.md` + candidate_store 的 `statistics.json`/`summary.json`。

---

## §5 ad-config 实例代码位置(请直接读代码,不在此拆业务细节)
- Optimizer 子类: `antomnievo/optimizer/adconfig/adconfig_optimizer.py`
- tunable_artifact_def: `antomnievo/model/tunable_artifact_defs/adconfig_tunable_artifact_def.py`
