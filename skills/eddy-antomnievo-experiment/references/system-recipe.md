# AntOmniEvo System 模块编写配方(后续阶段:用户确认冒烟无误后)

对应 AntOmniEvo 优化循环里的 **System** 组件:把一个候选 spec 跑起来、产出预测(trajectory + output)给 Evaluator 评分。本配方主要覆盖**"系统 = 调外部 generate.py 子进程"**这种形态(本项目的 eddy generate.py 就是这种,对标 text2sql)。其它形态(in-process agent / 容器化)照系统形态最像的一份 example 改结构。

> 这是 AntOmniEvo bootstrap(步骤 1–6)之后的接线活。写之前,步骤 1–6 须已完成(workspace + venv + AntOmniEvo 装好、数据层 + generate/evaluate 冒烟通过)。System/Evaluator/Proposer/optimizer 一起把 `await optimizer.optimize()` 跑起来。

---

## 0. 组件放哪:pip 装包 → `<exp_root>/antomnievo/<scenario>/`(统一约定)

AntOmniEvo 一律 **pip 装包**(`pip install ant-omnievo`;不拉源码 clone),本实验补充的组件**全部放专门目录 `<exp_root>/antomnievo/`**(默认;步骤 1 已布局好):

- 里面建本场景包 `<scenario>/`(如 `peizhiagent/`):System → `<scenario>/system/<domain>_system.py`,Evaluator → `<scenario>/evaluator/`,Optimizer 子类 → `<scenario>/optimizer/`,数据层 → `<scenario>/dataset/`,spec_def → `<scenario>/spec_defs/`,入口脚本 → `<scenario>/<domain>_optimize.py`,辅助脚本 → `<scenario>/scripts/`。
- 组件目录带最小 `pyproject.toml`,步骤 1 已 `uv pip install -e <exp_root>/antomnievo` 进 AntOmniEvo venv → 场景包直接 `import <scenario>.system...`;入口 `import antomnievo` 拿基类(pip 包)。**不要去改已装的包。**
- 参照结构从已装包里读:`<pkg> = $(<exp_root>/antomnievo/.venv/bin/python -c "import antomnievo,os;print(os.path.dirname(antomnievo.__file__))")`,看 `<pkg>/system|evaluator|optimizer|dataset|example/<既有 domain>/`(对标 `text2sql` / `rag_pipeline` / `terminalbench` / `appworld` 这些 domain 目录)。

---

## 1. 先读:看清 System 契约 + 找最像的 example

System 是 AntOmniEvo 五个可插拔接口之一。写之前**必读**(在 AntOmniEvo 仓库/包里):

1. `antomnievo/interface/system.py` — `System(ABC)` 抽象基类:只强求 `async _run(candidate_meta, data_inst) -> SystemResult`;基类提供 `run`(带信号量并发)和 `run_batch`(gather fan-out)。看清 `_run` vs `run_batch` 的关系。
2. `antomnievo/model/system_result.py` + `rollout_result.py` + `trajectory.py` + `usage_stats.py` — `SystemResult = {trajectory: Trajectory, output: RolloutResult, usage}`。`RolloutResult.content` 是"系统最终答案"(**str**,结构化对象先 `json.dumps`);`Trajectory` 是 **span 树**(`root_span_list: list[Span]`,`Span` 有 `name/span_type/input/output/children/metadata`,`Trajectory` 还有 `metadata/errors`)。
3. `antomnievo/model/candidate_data.py` 的 `CandidateMeta` —— **`candidate_meta.spec_dir` 是候选的可编辑 spec 目录**(你 load 回 runtime 的那个 `--spec-dir`)。
4. **最像的 example**(挑系统形态最像的一份照**结构**,不照字段):
   - "调外部 generate.py 子进程" 形态 → `antomnievo/system/text2sql/text2sql_system.py` + 入口 `antomnievo/example/text2sql/birdtest_text2sql.py` + `antomnievo/optimizer/text2sql/text2sql_optimizer.py`。
   - "最简单的 in-process agent" 形态 → `antomnievo/system/rag_pipeline/` 下那组。
   读 example 时重点看:构造参数怎么传(scenario-specific 路径在**构造时**给,不进 `run_batch` kwargs)、`run_batch` 怎么拼命令/怎么读回产物/怎么建 `SystemResult`。
5. **关键:看 optimizer 怎么调 system**。`antomnievo/optimizer/optimizer.py` 的 `Optimizer._run_and_evaluate` 调 `system.run_batch(meta, data_list)` **不传任何 kwargs**(纯 in-process 默认路径);scenario 子类(如 `Text2SQLOptimizer._run_and_evaluate`)override 它、造 tempdir、写 batch 文件、再给 `run_batch` 传 `output_dir`/`cases_path` 等 kwargs。**你写 System 的 `run_batch` 签名要跟你将来写的 optimizer 子类对齐**——System 和 Optimizer 是一对,配套写(见坑 1)。

---

## 2. 怎么写(子进程 generate.py 形态,对标 `Text2SQLSystem`)

- **override `run_batch`(不是 `_run`)**:跑一个 generate.py 子进程处理整批,比每条一个子进程高效。签名 `run_batch(self, candidate_meta, data_list, *, output_dir, cases_path, **kwargs) -> list[SystemResult]`(kwargs 跟你的 optimizer 子类对齐)。
- **构造参数**(scenario-specific,构造时给,全**绝对路径**):`generate_script`、`python_path`(业务项目 venv 的 python,generate.py 的 deps 在那)、`agent_src`、`editable`(步骤 3 约定的可编辑条目,list)、`local_source_repo`(写型 agent 的源码仓库)、`env_file`、`timeout`(单 case 超时)、`concurrency`(generate.py 的 case 级并发)、`local_sandbox_transport`、`no_install_deps`、`extra_args`。
- **拼命令**:`[python_path, generate_script, --agent-src, --spec-dir <candidate_meta.spec_dir>, --editable <ent>...(repeat), --cases <cases_path>, --output-dir <output_dir>, --concurrency, --timeout-seconds]` + 写型加 `--local-sandbox-transport --local-source-repo` + `--env-file`(可选)+ `--no-install-deps` + extra_args。
- **跑子进程**:`subprocess.run(cmd, capture_output=True, timeout=timeout*len(data_list)+300)` 用 `loop.run_in_executor` 包(别阻塞 event loop)。rc≠0 记 stderr 但别 raise(继续读产物,失败 case 在 SystemResult 里体现)。
- **读回**:`predictions.jsonl`(一行一 case,按 `case_id` 建 dict)+ `trajectories.jsonl`(一行一 case 的轨迹 dict)。
- **建 per-data_inst `SystemResult`**:按 `str(data_inst.id)` 匹配 case_id;`output=RolloutResult(content=json.dumps({case_id, prediction_present, run_status, final_text, artifact_source, artifact_summary(截断重数据), error}))`;`trajectory=<span 树,见坑 6>`;`usage=None`(generate.py 不产 UsageStats 就留 None)。
- **`_run` 也要实现**:`raise NotImplementedError`(你是 batch-only;别 `pass`,pass 会让误调用静默返回 None)。
- **`system_description()` + `Evaluator.scoring_criteria()` 必须准确反映 generate.py / evaluate.py 的机制**(你已写/读了这俩脚本,该懂原理 —— 见 SKILL『通用约定』):
  - `system_description()` 写清 agent 行为 —— 输入 / run-context 怎么来的、工具面 + 工作流、产出什么 artifact、在哪停(awaiting/HITL)、空产物的失败因(漏改而非崩溃)。
  - `scoring_criteria()`(Evaluator)写清怎么打分 —— 拿什么比、分数语义(0/1 各代表什么)、reason 来源、依赖什么前置(如 schema manifest)。
  - 这俩字符串注入 proposer / 分析 prompt —— **错或空会让它错误归因(把系统/数据问题算到 spec 头上)**。写 System/Evaluator 时一并写好,别留空 / 泛泛。

- ⚠ **eddy → AntOmniEvo Trajectory 解析: 用共享 parser,不要自己重写**
  - 代码位置: `antomnievo/common/utils/trajectory_parser.py` 函数 `parse_eddy_trajectory`
  - API:`parse_eddy_trajectory(raw_trajectory: dict, *, tool_output_max_chars=4000, root_output_max_chars=4000, pre_reasoning_max_chars=300) -> tuple[Trajectory, UsageStats]`
  - 你的 System 的 `_build_trajectory` 只是**一行调**:`return parse_eddy_trajectory(traj, tool_output_max_chars=self.X, ...)[0]`;别自己写消息扫描/工具配对/截断/错误检测 —— 都在 parser 里了。
  - 3 个 size 参数(作为 class 常量暴露给你的 System,用户可调):`tool_output_max_chars`(tool output 超就截,保 `output_truncated=True` flag)、`root_output_max_chars`(root output/final_text 截)、`pre_reasoning_max_chars`(每个 tool_call 前的 reasoning 累积文本截)。默认 4000/4000/300;调了让你看效果 + 成本权衡。
  - 输出结构:1 root span(`eddy_agent_run`) + N tool_call child spans(每个带 input=args / output=result(截断) / metadata `{tool_call_id, output_truncated?, output_original_len?, pre_reasoning?}` — **无冗余 `raw_tool_call`/`raw_tool_result`**)。root metadata 带 case_id/run_status/n_messages/content_type_counts/human_input_required。
  - 为什么有 `pre_reasoning`:proposer(pi+LLM)分析 agent 失败时,光看 tool 调用列表你看不到 "为什么 agent 跳过了验证、为什么选了 sibling config" 等决策原因。`pre_reasoning` 从 eddy 的 `type=reasoning` 消息流里按 tool_call 前后截一小段(val ~300 字)塞进 metadata,proposer 能看到 dive agent 思维,帮助定位 spec 问题。
  - 跟别的 parser 一样: `parse_stream_json` (claude CLI)、`parse_pi_json_output` (Pi CLI)、`parse_eddy_trajectory` (eddy) 共用 `Trait UsageStats + _collect_agent_errors`。

---

## 3. 坑(本形态 / eddy 特有,实测得的)

1. **generic `Optimizer` 不传 kwargs** → 必须配套写 optimizer 子类 override `_run_and_evaluate`(对标 `Text2SQLOptimizer`):造 tempdir → 写 `cases_path` → `system.run_batch(meta, data_list, output_dir=…, cases_path=…)` → `evaluator.evaluate_batch(…)`。System 的 `run_batch` 签名收 `output_dir`+`cases_path`。**别只写 System 不写 optimizer 子类**,否则 `run_batch(meta, data_list)` 没参数跑不了。
2. **`cases_path` 必须是完整 case 行(带 gold)**:generate.py 从 case 读 app/env/base_version(+ code_version 从 extra_context);evaluate.py 读 `expected.artifact.changes` gold。batch cases jsonl 用 `data_inst.to_case_dict()` 写(步骤 2 数据层保证它回原行)**,别只写 id/query**。
3. **`candidate_meta.spec_dir` = `--spec-dir`**:候选的可编辑 spec 目录;配 `--editable <pkg-rel>` 做 "load spec"(把候选面替换到 runtime checkout 上)。baseline 候选的 spec_dir 可以是 agent 包根本身(editable as-is)。
4. **写型 agent 要 `--local-sandbox-transport`**:只读 `LOCAL_WORKSPACE` 产不了产物(见 generate-evaluate-recipe 运行路径坑)。System 构造默认带 + `--local-source-repo`。冒烟前 sandbox 源码仓库要在、cases 里的 code_version 要能在那解析到。
5. **`SystemResult.output.content` 是 str,产物是结构化 → `json.dumps`**;重数据(target_config 之类)截断(别把 46k 全塞进 RunRecord)。⚠ **产物形态以实读为准**:本项目 generate.py 的 prediction-row `artifact` = `{all_change_summary, changes[0]{config_name/app/env/base_config_version/target_type/target_config/summary}}`——**别假设是 `payload.field_name`**(我第一次就猜错了,提取全 None)。**写提取前先实读一份 predictions.jsonl 确认 artifact 的真实键**;换领域形态会不同。
6. **`Trajectory` 用 span 树,别留空**(text2sql 留空是因为它没解析 eddy trace;eddy 有轨迹就该填)。把 tool_call 流做成 root 的 child `Span`(按 `tool_call_id` 配对 tool_result,input=args/output=result);其余(`message_summary`/`n_messages`/`human_input_required`/`run_status`)放 root span `metadata`;`errors` 标 error/timeout/空轨迹。proposer 靠 trajectory 分析失败,**空轨迹 = 没优化信号**。tool 事件优先从 trajectory 的 `tool_calls`/`tool_results` 取,没有再扫 `messages[].content[]` 里 `type==tool_call/tool_result`。
  - ⚠ **控制 trajectory 文件大小**(实测得的坑 — trajectory 一度数百 KB,其中大量是冗余 metadata + 大 tool output 没截断)—— trajectory 落盘进 candidate store 给 proposer 读;太大 = 浪 token + 浪磁盘。**两条规则**(共享 parser `parse_eddy_trajectory` 用 3 个 kwargs 控制):
    - **不冗余**:`span.input` 已有 tool args、`span.output` 已有 tool result → **不要在 `metadata` 里也拷 raw 全量**(那是 50% 冗余);metadata 只留 `tool_call_id` + 截断 flag + `pre_reasoning`。
    - **截断大输出**:`tool_output_max_chars`(默认 4000)超过就截 + 标 `output_truncated=True`。
  - **代码位置**:共享 parser `antomnievo/common/utils/trajectory_parser.py` `parse_eddy_trajectory()`;你的 System class 上加 `TOOL_OUTPUT_MAX_CHARS` / `ROOT_OUTPUT_MAX_CHARS` / `PRE_REASONING_MAX_CHARS` class 常量,调大 = 更多上下文给 proposer(代价 = 更大文件)。
7. **运行前置(model key + MCP 权限 + sandbox 源码仓库)**:generate-evaluate-recipe 坑节讲过;System 冒烟前同样要备齐,否则 `run_batch` 跑完 `prediction_present=False`(空跑,看着没崩但没产物)。
   - ⚠ **继承 shell 的旧 credential 会 shadow env 文件(实测坑)**:generate.py 的 dotenv 加载是 **shell 优先**(key 已在 os.environ 就跳过文件值)。若用户 shell 环境里有同名**旧** credential(如过期 IAM_TOKEN),System 起子进程时继承它 → 文件里的好 token 被 shadow → agent 中途报 MCP `无员工身份` 这类身份错误,且你手动 `source .env.local` 跑又是好的(覆盖了旧值),极难复现定位。**System 拼好 cmd 后:把 env 文件里声明的 KEY 从继承 env 里 pop 掉再 `subprocess.run(env=...)`**(只解析 KEY 名不读值),保证文件值生效。
8. **路径全绝对**:构造参数 + `run_batch` 的 `output_dir`/`cases_path` + `candidate_meta.spec_dir` 全绝对路径,子进程 cwd 无关。
9. **回到步骤 0 的组件目录**:写 `<exp_root>/antomnievo/<scenario>/system/<domain>_system.py`,入口从场景包 import。

---

## 4. 怎么验证写对了(必做,别跳)

1. **import + 子类校验**:`from antomnievo.system.<...> import <System>; issubclass(X, System)` 通过(基类契约 + pydantic 没破)。
2. **离线验 `_build_system_result`(用真产物最好)**:拿之前 generate 冒烟留下的 `predictions.jsonl`/`trajectories.jsonl` 喂 `_build_system_result`,断言 `SystemResult` 能构造(pydantic 过)、`content` JSON 可解析、artifact 字段提取对(对照 gold)、trajectory span 树 + tool_call 配对对。**这一步直接验真实 artifact 形态(坑 5),省一次 agent 跑**。
3. **端到端冒烟:实跑 `run_batch` 1 条 case**(真模型):造 `CandidateMeta(spec_dir=baseline 包根)` + batch cases(1 条,`to_case_dict()`)+ `output_dir`(`<workspace>/tests/system_smoke/`,见 SKILL『通用约定』),`await system.run_batch(...)`;断言:
   - 返回 `SystemResult` 数 == batch 数;
   - `prediction_present=True` + `artifact_summary` 对齐 gold(config_name / base_version / app / env / target_type);
   - trajectory 有 tool_call child span + `run_status` + HITL 捕获 + `errors` 空;
   - (写型 agent)`run_status` ∈ {completed, awaiting}。
   跑不过先分清:**运行前置没备齐**(MCP 403/无 VFS → `prediction_present=False`,去看 generate-evaluate-recipe 坑)还是**你提取/构造 bug**(对照真 `predictions.jsonl` 修,坑 5)。
4. 修了提取 bug 后**离线复验** `_build_system_result`(不必再跑 agent):拿同一份 predictions/trajectories 重跑提取,确认字段对——省时间。

---

## 5. ad-config 实例代码位置(请直接读代码,不在此拆业务细节)

- System: `antomnievo/system/adconfig/adconfig_system.py`
- 使用 `parse_eddy_trajectory` `(antomnievo/common/utils/trajectory_parser.py)` 做轨迹解析。

> 配套的 optimizer 子类怎么写见 optimizer-recipe。System 的 `run_batch` 签名务必和它对齐。
