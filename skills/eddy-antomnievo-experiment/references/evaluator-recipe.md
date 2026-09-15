# AntOmniEvo Evaluator 模块编写配方(步骤 8)

对应 AntOmniEvo 优化循环里的 **Evaluator**:接 System 的 predictions,打分(`score∈[0,1]` + `reason`)给优化循环选优 / 淘汰。本配方主要覆盖**"评分 = 调外部 evaluate.py 子进程"**形态(对标 text2sql;本项目 evaluate.py 就是这种)。其它形态(自带 scorer / in-process)照最像的一份 example 改结构。

> 接在步骤 7(System)之后;System + Evaluator 配套(optimizer 子类步骤 9 串起来)。

---

## §0 放哪 —— 组件目录(同步骤 7,统一约定)
- `<exp_root>/antomnievo/<scenario>/evaluator/<domain>_evaluator.py`(跟 System 同一场景包;参照结构读已装包里的 `antomnievo/evaluator/text2sql/` 等,不改已装的包)。
放哪在步骤 7 / system-recipe §0 已定;Evaluator 跟着走。

---

## §1 先读:看清 Evaluator 契约 + 找最像的 example
1. `antomnievo/interface/evaluator.py` — `Evaluator(ABC)`:`_evaluate(data_inst, system_result) -> EvaluationResult` 抽象;基类有 `run` / `evaluate_batch`(gather)、`scoring_criteria()` 抽象(返 str,注入 proposer prompt)。看清 `_evaluate` vs `evaluate_batch`。
2. `antomnievo/model/evaluation_result.py` — `EvaluationResult{data_id, metric_name, score∈[0,1], reason, usage}`。
3. **最像的 example**(子进程 evaluate 形态)→ `antomnievo/evaluator/text2sql/text2sql_evaluator.py`(它 override `evaluate_batch` 跑 evaluate.py 子进程、读 per-case 产物文件建 `EvaluationResult`)。看它怎么拼命令、读回产物、解析 score+reason。
4. **项目的 `scripts/evaluate.py` CLI + 输出**:看 `--help`(收什么 flag、跑什么 stage、写什么 output file)、⚠ **实读一份真 per-case 产物文件**确认 score / reason / id 键名 —— 别假设,每项目不同。
5. **看 optimizer 怎么调 evaluator**:`antomnievo/optimizer/optimizer.py` 的 `Optimizer._run_and_evaluate` 调 `evaluator.evaluate_batch(data_list, results)` **不传任何 kwargs**(纯 in-process 默认);scenario 子类 override 它、传 `output_dir`+`predictions_path`+`cases_path`。**你 Evaluator 的 `evaluate_batch` 签名要跟步骤 9 optimizer 子类对齐。**

---

## §2 怎么写(子进程 evaluate.py 形态,对标 `Text2SQLEvaluator`)
- **override `evaluate_batch`**(不是 `_evaluate`):签名 `evaluate_batch(self, data_list, system_results, *, output_dir, predictions_path, cases_path, **kwargs) -> list[EvaluationResult]`(kwargs 跟你的 optimizer 子类对齐)。
- **构造参数**(全**绝对路径**):`evaluate_script`、`python_path`(业务项目 venv python;evaluate.py 的 deps 在那)、`timeout`、`extra_args`;项目需要的话有项目特定的 flag(如 `schema_manifest`、`eval_stage`、`accuracy_threshold` 等 —— 看你 evaluate.py `--help` + 跟用户对齐,**别预设什么 flag**)。
- **拼命令**:`[python_path, evaluate_script, --predictions <predictions_path>, --cases <cases_path>, --output <output_dir>]` + 项目需要的项目特定 flag(从 `--help` 确认后加) + extra_args。
- **跑子进程**:`subprocess.run(cmd, capture_output=True, timeout=timeout)` 经 `loop.run_in_executor`(别阻塞 event loop);rc≠0 记 stderr 但不 raise(继续读产物)。
- **读回** `<output_dir>/`<你 evaluate.py `--help` 说写的 per-case 产物文件> → 按 per-case id 键建 dict;`data_list` 每条按 `data_inst.id` 匹配 → `EvaluationResult(data_id, metric_name, score, reason)`;**缺该 case → score=0 / "no evaluation detail"**。
- **score 归一化到 [0,1]**(项目 metric 可能 0–100 / EX×… 等 → 除上限 / 按项目确认);**`system_results` 不消费**(评分读 predictions 文件,同 Text2SQLEvaluator)。
- **`_evaluate`** raise NotImplementedError(batch-only,别 pass)。**`scoring_criteria()`** 准确反映 evaluate.py 打分机制(见 SKILL『通用约定』)。

---

## §3 坑(本形态 / 实测)
1. **generic `Optimizer` 不传 kwargs** → 配套写 optimizer 子类(步骤 9)给 `evaluate_batch` 传 `output_dir`+`predictions_path`+`cases_path`;Evaluator 签名收这三个 kwarg。**别只写 Evaluator 不写 optimizer 子类**,否则 `evaluate_batch(data_list, results)` 没参数跑不了。
2. **`predictions_path` = System 的 `<gen_dir>/predictions.jsonl`;`cases_path` = batch cases(全行带 gold,`to_case_dict()` 写,同步骤 7)** —— evaluate.py 读 `--cases` 的 gold。
3. **per-case 产物的 score/reason/id 键以实读为准** —— 别假设键名;每项目不同。先实读一份真 per-case 产物文件(per-case 产物 = 你 evaluate.py `--help` 说写的那个文件 —— 看项目的,不假设文件名 / 键名)。
4. **score 必须归一化到 [0,1]**(optimizer 要 [0,1] metric;项目 metric 可能是 0–100 / EX×(0.7+0.3*VES) → 按项目确认归一方式)。
5. **reason 要有信息量**(指名漏改 / 错改 / 多改哪个字段);空 / "correct" fallback = 坏信号(应来自项目 evaluator 的 detail 文案)。
6. **`eval_stage`**(项目特定的 stage flag,看你 evaluate.py `--help` 支持哪些 stage):fast 档(无 LLM,快)适合优化循环;detailed/full 档(可能含 LLM judge / runtime)慢 → 用不用、用哪档跟用户讨论 trade-off。**skill 不预设 stage 名**。
7. **项目特定前置 flag**(如 `--schema-manifest` / `--source-repo` 等):按你 evaluate.py `--help` 需要 + 跟用户对齐(**skill 不预设**);如果项目 evaluate.py 跑某阶段需要某个前置输入(如 pre-built manifest / repo path),没传就跑不下去 → 在构造参数 + YAML config 里都列上,跟 System 共用。
8. **`scoring_criteria()` 要机制准确**(见 SKILL『通用约定』;拿什么比、分数语义 0/1 各代表什么、reason 来源、依赖什么前置如 schema manifest)—— 错或空让 proposer 错误归因。
9. **`_evaluate` raise NotImplementedError**(别 pass → 误调用静默返回 None)。
10. 路径全绝对;eval 输出按『通用约定』放 `<smoke dir>/eval` 子目录(没 workspace → `/tmp`),保留不清给用户回看。

---

## §4 怎么验证写对了
1. `import` + `issubclass(X, Evaluator)` + `scoring_criteria()` 非空。
2. **离线**用一份真 per-case 产物文件(从之前 evaluate 跑留的产出,或步骤 6 冒烟的 `eval/`)喂 `_read` / 解析逻辑 → 验 `EvaluationResult` 字段对(score/reason/id 键对、score∈[0,1])—— 直接验真 schema,省一次 evaluate.py 跑。
3. **端到端** `evaluate_batch` 1 case 冒烟:复用步骤 7 System 冒烟的真产物(`<smoke dir>` 的 `gen/predictions.jsonl` + batch cases),`output_dir` 放 `<smoke dir>/eval`(没 workspace → `/tmp`),`await evaluator.evaluate_batch(...)`;断言:返回 `EvaluationResult` 数==batch 数、`data_id` 对、`score∈[0,1]`、`reason` 非空、(已知正确的 case)score 应高;evaluate.py 落盘的产物文件可看。
4. 修 bug 后**离线复验**(不必重跑 evaluate.py)。

---

## §5 ad-config 实例代码位置(请直接读代码,不在此拆业务细节)
- Evaluator: `antomnievo/evaluator/adconfig/adconfig_evaluator.py`

---

## §6 配套
optimizer 子类(步骤 9)怎么把 System + Evaluator 串进 `_run_and_evaluate`(造 tempdir → 写 batch cases → `system.run_batch(output_dir, cases_path)` → `evaluator.evaluate_batch(output_dir, predictions_path, cases_path)`)见后续 optimizer-recipe(待写)。Evaluator 的 `evaluate_batch` 签名务必和它对齐。
