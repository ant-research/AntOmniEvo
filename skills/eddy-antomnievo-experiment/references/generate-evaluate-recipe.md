# generate/evaluate 配方(eddy 专用)

在业务项目 `<proj>/scripts/` 下写 `generate.py` + `evaluate.py`。**本配方针对 eddy**:eddy SDK 相关的固定部分(`agent.invoke`、`AgentStates`、`RunContext`、`LOCAL_WORKSPACE`、包结构检测、dep-install、load-spec、轨迹)直接写死在 skill 里;业务变化部分(入口名、可编辑条目、运行上下文字段、converter、scorer、打分法)标为「问用户 / 从 gold 读」,不预设。

## 写之前:主动问用户

**写 generate.py 和 evaluate.py 之前,先问用户,别自己先一顿调查**(开口第一句就问,拿到用户指认后再针对性读代码验证;不要自己先把仓库翻个底朝天再开口):
1. 有没有可以参照的**系统运行脚本**(怎么跑 agent、怎么出 predictions/trajectories/workspace artifacts) —— 用户给路径或命令,你照它的输出格式/CLI 习惯写 generate。⚠ **参照 ≠ wholesale delegate**:**generate.py 必须自己写、自己实现 load-spec**(checkout + `--editable` 逐条替换 + 从 checkout import + 自己的 invoke 循环)—— 项目的现成推理脚本**不支持 `--spec-dir`/`--editable`**,直接委托它 = 候选 spec 载不进来,达不到 AntOmniEvo 的目标。对现成运行脚本的正确用法是**读它、复用它的机制**(prompt/运行上下文构造、sandbox-transport 挂载、converter/轨迹 builder 直接 import 调),不是 shell 出去。
2. 有没有可以参照的**系统评测脚本**(怎么读 predictions + gold、怎么打分、怎么出 per-case reason) —— 用户给路径或线索(grep `eval`/`score`/`judge`/`offline`/`predictions` 等),你照它的 metric 字段/reason 来源/CLI 参数写 evaluate。**evaluate.py 可以 delegate**(委托的前提 = 项目评测脚本能复用已有推理产物、不重跑 agent;具体支不支持、flag 叫什么看项目 eval CLI,以实际为准),不要自创一套不一致的 scoring。

**用户不知道时**:自己去仓库 grep 看,找到后列候选 → 跟用户确认 → 按上面分工写。**用户说"没有"时才从零写。**

---

## Eddy 固定部分(每个 eddy agent 都一样,直接写进代码)

### 必要的 eddy import + 调用
```python
from eddy.common.utils.context import RunContext
from eddy.types import AgentStates

# per case:
async def _run_one_case(agent, prompt, context, timeout):
    with RunContext(context):
        async for msg in agent.invoke(prompt, AgentStates(), hooks=[]):
            # 收消息;断流(终态)即停
            ...
```

- **`agent.invoke(prompt, AgentStates(), hooks=[])`** — eddy agent 的统一调用方式;`hooks=[]` 即不挂 hook(usage 捕获/别的 hook 看需要加)。
- **`RunContext(context)`** — 必须包在 `with` 里;eddy 的工具从 context 里读 `user_id`/`session_id`/`chat_id`/`env`/`target_app` 等。
- **终态判断**:`message["source"] is None and message["status"] in {"completed","awaiting","pause","error"}` → 本轮结束。
- **`final_text`**:从 `message["content"]` 里 `item["type"]=="text"` 的 `text` 拼。
- **超时**:`asyncio.wait_for(consume(), timeout)`。

### 必要的 eddy env 开关
- `LOCAL_WORKSPACE=1` — 用 `LocalWorkspace`、跳过 ARCA sandbox/VFS(本地跑必需)。
- 缺 model key 时用占位 key 让 `import` 不崩;真跑需真 key。
- `THETA_API_KEY`(或项目实际用的 key env var) — 模型 key;agent 在 **import 时**就 build 模型(ThetaModel),必须先有。
- `.env.local` / `.env` 用 dotenv 加载(**在 import agent 之前**,因为 starter_agent 在 import 时构造 MCP);格式:`KEY=VALUE` / `export KEY=VALUE` / `#` 整行注释 / shell 已 export 的优先。

### eddy 包结构检测(找 agent)
agent 入口形如 `<pkg>.<module>:<attr>`(eddy 约定,如 `agents.starter_agent:agent`);`--agent-src` 指向包含该包的目录。按结构(`<pkg>/__init__.py` + `<entry>.py`)在 `--agent-src` 下找,找到后把**包父目录**前插 `sys.path` + purge 同名缓存 → `import <pkg>.<--agent-module>:<--agent-attr>`。**不写死包名。**

入口名 + attr 是**业务变化的** → 问用户 / grep `builder.build()`/`AgentBuilder`/模块顶 `agent = ...`/读 `server-simple.yaml`/`CLAUDE.md` 等找,确认。

### dep 自动安装(import 前)
按 node_docs 范式:递归扫 `<pkg>` 下 `.py` 导入,丢 stdlib/本包/已装,`uv pip install --python <venv> <missing>`(best-effort)。`--no-install-deps` 可跳。这样新版本加新依赖也能直接跑。

### load spec(--spec-dir --editable,eddy 固定逻辑)
候选的可编辑改动按 `--editable`(可重复,pkg-rel 条目)逐条**替换**到 runtime checkout:
1. 拷一份运行期包到 tmp(跳 `__pycache__`/重数据;重数据 symlink 回源,不每 rollout 拷)。
2. 每个 `--editable ent`:**dir → `rm <checkout>/<pkg>/<ent>` + `copytree(`<spec-dir>/<ent>`,…)`**;**file → `rm` + `copyfile`**;candidate 没有的条目 → 只 `rm`(删除传过去)。不 merge。
3. 从 checkout import agent + invoke。

---

## 写法范式:流式写盘(强制 —— 否则"结果一个都没有"/内存爆)

`generate_predictions`(每条产出**完整 trajectory,几百 KB、带 messages**)只有一种**强制**写法 —— 这套针对"大 payload 攒内存会 OOM"的 **generate**;项目 eval pipeline 的并发 judge **另说**(结果通常 KB 级,见下小节,**能跑就别改、别硬套这套**):

> **异步并发(有界:`Semaphore`/workers)、完成一条立即 append 写盘并释放大对象、全部跑完再做聚合(读回 + 按需重排 + 算 summary)。禁止 `asyncio.gather` 把全量 case 的 row+完整 trajectory 攒内存、最后 `write_text` 一次写。**

- **并发机制(关键判据)**:并发主体的耗时是"**等远程调用**"(LLM / MCP / HTTP)= **I/O 等待**时,**纯 async 一把 `await` 就够**;`ThreadPoolExecutor`(线程 + 每条 `asyncio.run` 起停 event loop)**是多余的** —— 线程不帮 I/O-wait(GIL 在 await 时本就释放),一个 event loop 用 `Semaphore` 多路复用更轻、无嵌套 loop。**新写并发代码:优先纯 async**(本 generate 就这么写);`ThreadPoolExecutor` 能用,但别拿 I/O 等待去配它。能跑的既有代码(无论线程还是 async)**留着别动**(见 judge 小节)。
- **为什么流式(尤其 generate)**:① N 条完整轨迹全攒内存再写 = OOM;② `predictions.jsonl` 只在跑完才出现 → 中途"结果一个都没有"的假象;③ 崩了也有部分产物、可分段评。
- **症状 → 根因**:`predictions.jsonl` 一直 0 行、到快结束才一次性长出 = 写成了 gather-then-write-once → 改成下面的增量写。

### generate.py 流式骨架(eddy 通用)
```python
sem = asyncio.Semaphore(max(1, args.concurrency))
pred_file = output_dir / "predictions.jsonl"; traj_file = output_dir / "trajectories.jsonl"
pred_file.write_text("", encoding="utf-8"); traj_file.write_text("", encoding="utf-8")  # truncate: 同 dir 重跑干净起
write_lock = asyncio.Lock()
counters = {"done": 0, "failed": 0, "n_predictions": 0}   # 聚合用;锁内自增
async def _gated(case):
    async with sem:
        row = await _run_case(...)                    # 重活
    traj = row.pop("_trajectory", {})                 # 大对象,本函数内用完即释
    run_status = (row.get("inference") or {}).get("run_status", "")
    lp = json.dumps(row,  ensure_ascii=False, default=str)
    lt = json.dumps(traj, ensure_ascii=False, default=str)
    async with write_lock:                            # 串行化 append
        (traj_dir / f"{safe_name(row['case_id'])}.json").write_text(lt, encoding="utf-8")
        with traj_file.open("a", encoding="utf-8") as tf: tf.write(lt + "\n")
        with pred_file.open("a", encoding="utf-8") as pf: pf.write(lp + "\n")
        counters["n_predictions"] += 1; counters["done"] += 1   # 锁内自增(单线程/互斥安全)
        if run_status in {"error", "timeout"}: counters["failed"] += 1
        logger.info("case %d/%d done — %s — predictions.jsonl now %d rows", counters["done"], len(cases), row.get("case_id"), counters["n_predictions"])
    return {"case_id": row.get("case_id")}             # gather 只回收小 status
await asyncio.gather(*(_gated(c) for c in cases))      # 大 row 已 per-task 释放;内存只占 concurrency 那几条
# 聚合在后:run_summary 从计数器取,结尾写一次
```
等价写法:`tasks=[asyncio.create_task(sem_wrap(_process_one(c))) for c in cases]; for coro in asyncio.as_completed(tasks): x=await coro; <立刻写盘>; pbar.update(1)`,最后读回磁盘聚合。关键是**完成即写 + 不攒大 row + 聚合在后**。

### 项目 eval pipeline 里的并发 judge:能跑就别动,别为"对齐风格"改并发机制
evaluate.py 薄壳不动(它读盘、不攒)。项目 eval pipeline 里**既有的并发 LLM judge 模块**(`ThreadPoolExecutor` 或 asyncio workers,常"全部跑完 `write_jsonl(path, results)` 一次写"):
- judge 的 per-case 结果通常 **~KB 级**(score + reason + 维度),**原版"跑完一次写"不构成内存问题** → **能跑就别改**。流式是 generate(完整轨迹几百 KB)才必须;judge 不是 → 不必"修"。
- **尤其别为"对齐纯 async 风格"把既有 `ThreadPoolExecutor` judge 改 asyncio**(要把 `judge_case` / `JudgeClient` 签名 sync→async、动重试 / trace / timing,风险高、对评分无收益)。`ThreadPoolExecutor` 在 I/O 等待型下虽多余但能用、且已验证 → **留着**。
- **只有当**:(a) 你已在重写该 judge 且想加分段落盘 / 崩溃保留;(b) 或它真累积大 payload —— 才按上面流式范式改:每判完一条 `open("a")` append → 跑完 `read_jsonl` 读回 + **按 cases 输入顺序重写最终文件**(用 `write_jsonl` 覆盖成原序、byte 一致;thread 用 `threading.Lock`、async 用 `asyncio.Lock` 串行化 append)→ summary 在后。改时:**增量 append 的序列化必须 == 该模块既有 `write_jsonl` 的序列化**(逐项核对 `ensure_ascii`/`separators`/`default`,**实读该代码、别预设,不同项目实现不同**)。

### 验收(改完必跑 —— 否则不知道有没有真改对)
1. `py_compile` 改过的文件全过。
2. import-smoke:`<venv>/bin/python -c "import importlib,importlib.import_module('<mod>')"` 捕 import 期错。
3. **流式 smoke**:`--limit 2`(写型 agent 配 `--local-sandbox-transport --local-source-repo <src>`),跑起来立刻看日志 + `wc -l predictions.jsonl` —— 必须看到**逐条 case 完成 + `predictions.jsonl` 行数逐条增长**。**没有逐行增长 = 没改成增量。**
4. 真产物校验:首几条 case 的 `workspace/.../artifacts.jsonl` 有真实 `artifact_type`(写型 agent 要有它该产出的写类产物,非合成)—— **具体产物类型名以该 agent 业务为准**(配合 §坑 "`n_failed`≠有产物" 判)。
5. evaluate 跑完拿到总平均分(per-case `score`+`reason` 合理)—— summary 字段名 / 归一换算 **以该项目 evaluate.py 实际产出为准**,别套别的项目。

---

## 业务适配部分(每个业务不同;问用户 / 从 gold 读)

### 运行上下文(从 case gold 读,不写死业务默认)
Eddy 的 `RunContext(context)` 里要填的 `context` dict:
- **eddy 固定**:`user_id`、`session_id`、`chat_id`(用于 workspace/产物路径)、`env`、`target_app`/`app_name`、`domain`。
- **业务适配**(从 case 的 gold 字段读,别写死):`app`/`env`/`domain`/`base_config_version` 等业务字段,因领域而异 → 读 case 里的 `expected` / `extra_context`,或问用户该填什么;CLI flag(`--app-name`/`--env`/`--domain`)仅作 override,默认空。

### converter(复用项目已有)
若业务项目已有"原始产物 → 评分用 changes"的转换(比如某 `scripts/eval/stages/prediction.py`),直接调用,把它的输出放进 `predictions.jsonl` 的 `artifact`,**别重写转换逻辑**。具体调用哪个、输出字段名,是**业务变化的** → 问用户 / 读项目已有代码确认。

### evaluate 委托(业务变化的:哪个 scorer、取哪个 metric)
- **写之前先跟用户对齐"怎么打分"**(跟找入口同款;不预设打分法):
  ① 让用户给一个 `期望产物 vs 真实产物` 的对比例子。
  ② 或去仓库 grep `eval`/`score`/`grade`/`judge`/`predictions`/`offline` 等,把候选列给用户确认:哪个是正确的打分法 + 输入/输出契约。
- **委托 + 解析**:subprocess 或 import 调用户确认的 scorer/pipeline(不重跑 agent);读它产出的 summary + per-case results;`EvalResult.score∈[0,1]` = 把确认的 metric 归一化(问用户:除某上限? 或本就是 [0,1]?);`reason` 从它 per-case 产物里确定性文案抽。
- **自创 shallow(项目没 scorer 时)**:只按用户给的对比例子把"对/不对"判成确定性规则,per-case `score∈[0,1]` + `reason` 指名。把判定规则写清给用户确认。

---

## 必要参数清单(generate.py)

| 参数 | 必填? | eddy/业务 | 说明 |
|---|---|---|---|
| `--agent-src` | 必填 | eddy 固定 | 运行期包目录(包父目录上 sys.path;import agent 包) |
| `--agent-module` | 有默认,业务适配 | eddy 约定 `agents.starter_agent`;实际问用户确认 | agent 所在的模块路径(相对 pkg) |
| `--agent-attr` | 有默认 `agent` | eddy 约定 | attribute 名 |
| `--cases` | 必填 | 业务适配 | 评测集 jsonl(gold) |
| `--output-dir` | 必填 | — | 输出目录(用户确认的) |
| `--limit` | 可选 | — | 只跑前 N 条 case |
| `--concurrency` | 可选 | — | 默认 1(case 内并发) |
| `--timeout-seconds` | 可选 | — | 单 case 超时;默认 3600s(agent 跑一轮多 step + 工具 + LLM 调用容易超过默认值;完整跑一条 case 走 evidence→draft→edit→post-validation 等多 step 通常 10–20 分钟,3600s 是对 agent 跑一个真实 case 的安全超时 |
| `--spec-dir` | 可选 | eddy 固定逻辑 | 候选的可编辑 spec 目录 |
| `--editable` | 可选,配 `--spec-dir` | 业务适配(步骤 3 约定) | pkg-relative 可编辑条目,可重复 |
| `--env-file` | 可选 | — | dotenv 文件,可重复;在 import agent 前加载 |
| `--dry-run` | 可选(仅开发自测) | — | 不调 agent,种合成 artifact;**冒烟不用 `--dry-run`** —— 必须真跑 agent 产真实数据 |
| `--app-name`/`--env`/`--domain` | 可选 | 业务适配,仅 override | 从 case gold 读而非写死 |
| `--no-install-deps` | 可选 | — | 跳 dep auto-install |
| `--keep-secaspect` | 可选 | eddy | 不关 antmcp secaspect(默认关) |
| `--local-sandbox-transport` | 可选 | eddy | **写型 agent 用**:走 SandboxWorkspace + 本地 transport(patch `get_operator` 挂本地可写 VFS)让 agent 能产写类产物。需配 `--local-source-repo` |
| `--local-source-repo` | 配 sandbox-transport | 业务适配 | 项目源码仓库 checkout 路径;按 case 基线源码版本导出快照、映射 sandbox I/O |

## 必要参数清单(evaluate.py)

| 参数 | 必填? | eddy/业务 | 说明 |
|---|---|---|---|
| `--predictions` | 必填 | — | generate 的 predictions.jsonl |
| `--cases` | 必填 | 业务适配 | gold 的 cases jsonl |
| `--output` | 可选 | — | 输出 summary + per-case 产物(具体文件名/键名看项目 evaluate.py `--help` + 实读真产物确认) |
| `--accuracy-threshold` | 可选 | — | 默认 0.95 |
| `--case-id`/`--max-cases` | 可选 | — | 选子集 |
| *(委托项目 eval pipeline 时的传透参数;stage/flag/字段名都以项目 eval 为准,问用户)* | | | ask 用户 |

---

## 通用参数与能力:为什么这么设计(给用户解释用)

generate.py / evaluate.py 有一套**通用参数 + 能力是每个 eddy 业务都该有的** —— 别的业务生成 gen/eval 时直接照搬这套,只改业务适配部分(入口名 / 可编辑条目 / 运行上下文字段 / converter / scorer)。下面每条都附**为什么**,方便你跟用户解释"为什么这么做"。

### generate.py 通用参数(直接复用)

| 参数 | 为什么要有 |
|---|---|
| `--agent-src <运行期包目录>` | 按结构(`<pkg>/__init__.py` + `<entry>.py`)找包、不写死包名 → 不同业务/不同版本的包名都能适配;版本隔离也靠它(每版本一个目录)。 |
| `--agent-module` / `--agent-attr` | 入口是 import 锚 + code-integrity 锚;不假定叫 `agents.starter_agent:agent`,问用户/grep 确认。 |
| `--cases <gold jsonl>` | 评测集(含 gold)。 |
| `--output-dir <d>` | 本轮所有产物(`predictions.jsonl`/`trajectories.jsonl`/`workspace/`/`run_summary.json`)都落这;**每次跑、每个候选必须独立 dir**,否则产物相撞(AntOmniEvo 一候选一 process 一 dir)。 |
| `--limit N` | 只跑 cases 的前 N 条;冒烟传 `--limit 1` 省钱省时,全量评测不传(默认全跑)。 |
| `--concurrency C` | 单 process 内多 case 并发(默认 1);⚠ 共用一把 model key 时,网关限流会让"慢 case"伪装成"差 case",AntOmniEvo 多候选(多 process)并发时尤其要保证 key 公平、限流可观察。 |
| `--timeout-seconds S` | agent 一条 case 走 evidence→draft→edit→validate 多 step + 多次工具/LLM,常 10–20 分钟;给单 case 一个 `asyncio.wait_for` 安全超时,防一条卡死拖垮整批。 |
| `--spec-dir <候选 spec 目录>` + `--editable <pkg-rel>`(可重复) | **不给 `--spec-dir` = smoke 模式**,跑 runtime as-is;**给 `--spec-dir`(必配 `--editable`)= load 候选 spec**:把候选改过的可编辑面**替换**到不可编辑的 runtime checkout 上再跑(AntOmniEvo 候选 = 改过的可编辑面,只有 load 回 runtime 才跑得起来)。用 `rm + copytree` / `copyfile`(**不 merge**)才能让候选的删除/改名传过去;`--editable` = 步骤 3 跟用户约定的可编辑条目。 |
| `--env-file <f>`(可重复) | agent 在 **import 时**就 build 模型/构造 MCP,它读的 key 那时必须在 env 文件或 shell 里 → **必须在 import agent 前加载**;格式 `KEY=VALUE`/`export`/`#` 整行注释;shell 已 export 优先(让真凭证盖过文件占位)。 |
| `--dry-run` | 不调 agent、种合成 artifact,让 converter+evaluate 零模型跑通(开发自测用);⚠ 冒烟必须真模型,不用它。 |
| `--app-name`/`--env`/`--domain` | 运行上下文业务字段因领域而异 → 默认从 case gold 读、不写死;flag 仅作 override。 |
| `--no-install-deps` / `--pip-index-url` | import 前扫包的第三方导入、`uv pip install` 缺失的 → 新版本加新依赖"just works";AntOmniEvo 并发多候选时先一次性 pre-flight 装齐、再 `--no-install-deps`,避免共享 venv 写竞争。 |
| `--local-sandbox-transport` + `--local-source-repo` | **写型 agent 用**:只读 LocalWorkspace 产不了产物;把项目源码仓库按 case 基线源码版本导出本地、patch sandbox operator 映射 I/O → agent 看到可写 sandbox + 真基线,能产真 artifact。 |
| `--keep-secaspect` | 默认关 MCP 安全切面提速;但 server 侧 gateway 仍查身份+权限,关客户端切面绕不过 server 门。 |

### generate.py 通用能力(直接复用)

- **`agent.invoke(prompt, AgentStates(), hooks=[])` 包 `RunContext`** — eddy agent 统一调用方式;`RunContext` 给工具提供 `user_id`/`session_id`/`chat_id`/`env`/`target_app` 等。
- **终态判断**(`source is None and status in {completed,awaiting,pause,error}`)+ **final_text 拼装** — 知道一条 case 何时结束 + 提取最终文本。
- **单 case 失败不连累**(try/except → 记 error → 继续下一条) — 一条崩不能毒死整批;失败也落 prediction row 供分析。
- **trajectories.jsonl 必写**(per-case 消息流,统一一个文件) — AntOmniEvo proposer 读失败轨迹分析"改什么";没轨迹就没优化信号。
- **复用项目已有 converter**(项目里"原始产物 → 评分用 changes"的转换函数) — 不重写转换,跟项目 eval schema 一致;converter 具体是哪个问用户/读项目代码。
- **运行上下文从 case gold 读**(data-driven) — 业务字段不写死。

### evaluate.py 通用参数(直接复用)

| 参数 | 为什么要有 |
|---|---|
| `--predictions` / `--cases` / `--output` | 读 generate 产物 + gold,写 summary + per-case 产物文件(文件名/键名看项目 evaluate.py `--help`,别假设) |
| `--case-id` / `--max-cases` | 子集评分(冒烟只评 1 条)。 |
| `--accuracy-threshold`(默认 0.95) | optimizer metric 门槛(`meets_threshold` 判定用)。 |
| *(委托项目 eval pipeline 的传透参数)* | 每个项目 eval pipeline 不同(stage/flag/字段名以项目为准),问用户;别套别的项目的。 |

### evaluate.py 通用能力(直接复用)

- **委托项目自己的 eval pipeline**(subprocess 或 import 调它,**不重跑 agent**) — 不自创 scoring;复用项目已验证的 scorer;`evaluate` 只负责"读它的产出 + 归一化成 optimizer metric + 抽 reason"。
- **`EvalResult.score∈[0,1]` 归一化** — optimizer 要 [0,1] metric;问用户怎么把项目的 metric 归一化(除某上限? 还是本就是 [0,1]?)。
- **`reason` 有信息量**(指名漏改/错改/多改了哪个字段;文案来自项目 evaluator 的 failure_detail / LLM scorer/judge,不是空泛 fallback) — optimizer/proposer 要可行动信号,reason 不能只写 "correct"/"incorrect"。
- **打分法/指标名不预设** — 跟用户对齐"怎么算对"(对比例子 / 项目已有 scorer),每项目不同。

---

## 轨迹(trajecories)——是必需的
agent 的消息流**必须落盘**(regardless of `--dry-run`):AntOmniEvo 的 proposer 后面会读失败轨迹分析为什么要改 + 改什么。没轨迹就没优化信号。所以:
- generate.py 默认就写 trajectories(不提供一个 `--no-trajectories`)。
- per case 的消息流 dumped 成 json(每条消息的 `content`/`tool_calls`/`tool_results`/`human_input` 全留),写到一个**统一的** `trajectories.jsonl` 文件(不要 per case 分散):
  ```
  trajectories.jsonl = [
    {"case_id":"case_001", "case":..., "run":..., "output":{"final_text":...}, "workspace_file":..., "message_summary":..., "tool_calls":[...], "tool_results":[...], "human_input_required":..., ...},
    ...
  ]
  ```
  这个 schema 照你项目既有 eval pipeline 的轨迹预测那行(build_trajectory 那类函数的输出),后面 evaluate 委托 eval pipeline 时可以直接用 `--reuse-trajectories` 吃它,不需要转换。

---

## 产物文件形状

| 文件 | 内容 |
|---|---|
| `predictions.jsonl` | `{case_id, status, prompt, final_text, artifact, artifact_source, run:{...}}` |
| `trajectories.jsonl` | 每条 case 的消息流(上面 schema;**必需**,optimizer 读) |
| `run_summary.json` | `{agent_src, package, agent_file, spec_loaded, spec_dir, editable, checkout, n_cases, n_failed, predictions, ...}` |
| `workspace/<user>/<session>/artifacts.jsonl` | agent 工具落盘的原始产物(喂给 converter) |
| `eval_summary` | `{score∈[0,1], ...}`(文件名/字段以你 evaluate.py `--help` 实际产出为准,别假设) |
| per-case 产物 | 每条有 `score` + `reason` +  case-id(字段名以你 evaluate.py 实际产出为准) |

---


## 坑(eddy 固定经验)

### 选运行路径:只读 LocalWorkspace vs sandbox-transport(按 agent 是否"写产物"决定)
eddy agent 产不产"写类产物"决定本地跑选哪条路径 —— **先搞清这点再冒烟**,否则卡在"agent 跑完但没产物"或直接 VFS 报错。判据:产物是"调工具写 config/source edit / 出 release ticket"(写型)还是"纯检索/推理回答"(只读型)。看 workspace `artifacts.jsonl` 的 `artifact_type`(写型有 edit_result / patch / ticket 之类)+ 问用户确认。

- **只读 LocalWorkspace 路径**(`LOCAL_WORKSPACE=1`,跳过平台 sandbox):够用于只读型 agent。**不能产写类产物**:写工具落不下去,或 agent 的 workspace 模块在 eval 模式下要求 source VFS 而报 `eval mode requires a source VFS but none is attached` 之类。
- **sandbox-transport 路径**(写型 agent 用):把项目源码仓库按 case 的**基线源码版本**导出一份到本地、patch `SandboxWorkspace.get_operator` 把 sandbox I/O 映射到这份本地快照(可写) → agent 看到"挂了真基线源码的可写 sandbox",能跑完整 edit→draft→artifact 链路、产真 artifact。case 的基线源码版本必须能在源码仓库里解析到(本地已有 commit 或可 fetch)。
  - "挂本地 VFS" 这套机制通常是**项目自己已有的**(项目里跑 offline eval / 本地推理的脚本里,带"patch sandbox operator / 挂本地可写 VFS"这类函数) —— **复用它,别重写**;generate.py 把"是否走 sandbox-transport"做成一个 flag 接进来即可(flag 名以项目 generate.py 为准)。
- ⚠ **别犯反向错**:对写型 agent 只设 `LOCAL_WORKSPACE=1` 就当能跑 —— agent 会 `status=completed` 但 `prediction_present=False`(没产物),看着"没报错"实则空结果(见下"`n_failed=0` ≠ 有产物")。

### MCP 身份 + 权限(agent 用 MCP 时,冒烟前必须就绪)
agent 用 eddy MCP server 时光有 model key 不够 —— MCP 还要两层放行,缺一就跑不出真产物,且常**不 fatal**(agent 退到本地工具瘸腿跑完,看着"没崩"但没产物):
1. **身份 token 有效**:MCP gateway 要从身份 token 认出员工/调用方(常见带工号/序列号类 claim)。token 损坏/缺 claim → 认不出身份(identity rejection 类)。
2. **账号有该 MCP 权限**:身份认出后,账号还得有每个要用的 MCP server 的权限 → 否则 `403 NO_PERMISSION` 类。
- 两者都在 **agent invoke 启动后几秒内**出现在日志(连 MCP → list_tools 那几行)。冒烟前跟用户确认:身份 token 有效 + 账号已申请并拿到每个要用的 MCP server 权限;缺就让用户先申请,别反复盲跑。
- generate.py 默认关**客户端侧** MCP 安全切面(secaspect),但 **server 侧 gateway 照样查身份+权限** —— 关客户端切面绕不过 server 门。
- **蚂蚁内部拿 MCP IAM token 的方法(用户授过权的标准做法)**:浏览器打开内网授权页 `https://login-intranet.alipay.com/pub/oauth/AppAuthorize.htm?token=<app-token>`(授权页 URL,token 参数是应用授权标识,过期/失效就让用户给新的),页面里**粘贴 `mcpnexus.alipay.com`** 作为目标,完成认证(刷脸)后拿到 IAM token。很多 eddy 项目脚本已内置该流程(如 `--open-iam-token-page` 打开授权页 / `--prompt-iam-token` 打开+等待粘贴+自动写 `.env.local`,target 常量就是 `mcpnexus.alipay.com`)—— **优先让用户走项目自带流程**,没有就把授权页 URL 给用户。⚠ token 是长 JWT,**聊天粘贴通道可能截断**(实测:三次粘贴都恰好停在同一总长 → 截断在源头);拿到后**先解码验 3 段 + 签名段长度 + `exp` 剩余时间**,有问题让用户走"写文件/终端粘贴"通道,别拿截断 token 反复盲跑。

### eddy agent 的"两套 MCP 面"(别把 allowlist skip 当 bug)
eddy agent 常把 MCP 暴露成两套:
- **eddy MCP 模块面**:直接给 LLM 用的 MCP 工具,经 allowlist 过滤(日志 `skip MCP tool ... by allowlist` 是**设计如此**,不是 bug —— LLM 不直接调原始 MCP 工具)。
- **tool 层 MCP 客户端面**:包在 `@function_tool` 里的 MCP client;agent 真正的 read/edit 流程通常走这套(程序化调 MCP),不是 LLM 直调。
→ 看到 `skip ... by allowlist` 别当 blocker;agent 真正用 MCP 的入口是那些 wrapper `@function_tool`。找它:在 agent 包里 grep MCP client helper + 调它的 `@function_tool`(产 edit/draft/ticket 的那些)。

### token / 长串 secret 别手敲进 env 文件
把 key/token(常是长 JWT / 不透明串)写进 `.env.local` 时,**按精确值替换**(脚本读文件改值 / 原样变量),**不要手敲重输** —— 一个 base64 字符打错就坏 3 字节:签名失效 + claim 丢(如工号类 claim 没了),且表现为"无身份"这种看不出根因的错。写完用**字节级相等比对**确认 +(JWT 的话)解码 payload 确认关键 claim 还在。

### IAM/MCP token 过期 → 分数系统性异常低(跑前先解码 exp)
eddy agent 用 MCP 时,身份/权限类 token 常是 JWT,**过期不会报错**,只是 MCP 挂、agent 退本地瘸腿跑完 → **所有 case 分数系统性异常偏低**。跑前先解码 `exp`(`base64` `urlsafe` decode `payload.exp`)对比 `now`,`<2h` 立刻换,别盲跑。看到全 batch 分系统性异常偏低 → **第一反应查 token 是否过期,别去改 agent**。

### uv venv:别 `uv sync`(会剪掉 requirements.txt 的 deps)
不少 eddy 业务项目 `pyproject` 声明 0 依赖、真运行 deps 在 `requirements.txt`;`uv sync` 按 `uv.lock` 只装 project 依赖 → 把 `requirements.txt` 已装的(ant-eddy / arec / antmcp / pylet 等)**剪掉** → import 崩。正确:工作 venv 已装齐时 generate 加 `--no-install-deps`;要补装用 `uv pip install -r requirements.txt --index-strategy unsafe-best-match`,**之后别再 `uv sync`**。

### `n_failed=0` ≠ 有产物;`awaiting`/`pause` 是 HITL 停点不是失败
- `run_summary.n_failed=0` 只代表"没 case 报 error/timeout",**不代表产了真 artifact**。写型 agent 在缺运行前置(没可写 VFS / MCP 没权限)时会 `status=completed` 但 `prediction_present=False` / `artifact=null` → 实际 0 / 漏改。**判冒烟有没有真产物,看 `predictions.jsonl` 的 `prediction_present` + workspace `artifacts.jsonl` 的 `artifact_type`,别只看 n_failed。**
- `run_status=awaiting`/`pause` = agent 在 HITL/确认闸门停住(如 release/push 类动作前等确认) —— **artifact 往往已产出、可评分**,闸门停是预期(这类动作冒烟本来就不该 auto 执行)。别当失败。
- 写型 agent"跑完但空产物" → 多半是运行前置缺失(只读 LocalWorkspace 没可写 VFS / MCP 没权限),**去补前置,别改 agent**。

### evaluate 是"委托项目自己的 eval pipeline",别把项目特定的 stage/flag/字段写死
- evaluate.py **委托项目自己的 eval pipeline**(不重跑 agent;打分法/取哪个 metric/stage/flag 全跟用户对齐,**本技能不预设任何 stage 名 / flag 名 / 评分字段**)。不同 eddy 项目的 eval pipeline 长得很不一样(有的有多 stage + LLM judge、有的只有确定性比对;有的要 schema descriptor、有的不要)—— **照用户确认的那套来,别把某个项目的 stage/flag 当通用**。
- **先快后全**:先跑项目 eval 里"快、无 LLM"的那档确认"产物对不对";要多维(含 LLM judge 之类)再跑全档(需 model key + 更久)。具体档位怎么切、叫什么、flag 是啥 —— 问用户/看项目 eval CLI。
- **数据前置坑(通用形态)**:eval 的某个阶段可能要求 case 上带**结构化字段**(如基线版本、产物类型之类),而 generate 往往把这些信息放在 case 的 context 文本里读、**没进该字段** → eval 报"缺字段"。修法:看项目 eval 是否支持"复用预建中间产物"之类的 flag(跳过该阶段),或用一份带结构化字段的 cases。**具体字段名/flag 名问用户/看项目 eval 代码,别套别的项目的。**
- **判 score 是不是真比对**:读 eval 的 per-case 比对明细(equal/diff 之类)确认是真比对、不是松判;高分要能对应到"预测 vs gold 逐项相等"的证据。
- **多维分低于阈值 ≠ agent 错**:full/多维分不到阈值,可能是某个**非"产物正确性"维度**拖的分(如"是否真执行了需 HITL 确认的动作"—— 冒烟里 agent 正确地没 auto 执行发布/上线类动作,那个维度就低) —— 区分"产物错"(正确性维 <1)vs"没执行 gated 动作"(执行维 低)。**别把后者报成"agent 错"。**

### 轨迹要复用项目既有 schema(不要自己简化产出)
- generate.py 必须产 `trajectories.jsonl`(一行 per case)——这个文件后续要被 evaluate 委托给项目的 eval pipeline 处理:evaluate 委托的项目 eval pipeline 里 LLM-scorer / per-case 分析 要从中抽取 trajectory events / tool_calls / tool_results / human_input 等。
- **如果你简化产出(只塞 raw `messages` 字段、缺 `tool_calls` / `tool_results` / `message_summary` / `human_input_required` 等结构化字段),evaluate 委托的 项目的 LLM scorer / judge 会判 "轨迹完全为空"**,拿到空轨迹就打 0 分 —— 这些数据就有误导价值了。
- 复用方法:如果项目有 `prediction.convert()` / `prediction.build_trajectory(row)`(edd+y agent 项目常见,位于 `scripts/prediction.py` 之类)的话,generate.py 内部直接 import 调用它 → 走项目既有 trajectory schema,不要自己手搓。没有的话,你至少要照 `prediction.build_trajectory` 的输出 schema 字段(`case_id` / `case` / `run` / `output` / `workspace_file` / `selected_artifacts` / `turn_index` / `query` / `answer_list` / `message_summary` / `tool_calls` / `tool_results` / `human_input_required`) 手动抽装一份。
- 如果项目 schema 你对不上,先停下来跟用户对齐:把 generate 已得的产物(predictions + raw messages)给用户看,问"你项目的 eval pipeline 需要 trajectories.jsonl 长什么样" —— 不要凭运气。

### 冒烟完成后的自查
跑完 generate + evaluate 后,**先自查这几件东西在不在**(注意:`n_failed=0` 只代表没报错,不代表产了真产物):
1. **真产物**:`predictions.jsonl` 的 `prediction_present=True`,且 workspace `artifacts.jsonl` 里有真实的 `artifact_type`(写型 agent 要有 edit_result / patch / ticket 之类),不是合成的。
2. **轨迹**:`trajectories.jsonl` 有真实消息流(非空,含 tool_call / tool_result / reasoning / text),不是合成的。
3. **评分**:summary 产物的 `score`∈[0,1]。0 不一定是 bug(agent 真没产对产物时 0 是对的);1 也不一定"通过"(可能你打过 mock)。看 `score` 和 `reason` 是否自洽:
   - 0 分 + reason 说"漏改 / 未产出" → 真 0(agent 没产对)。
   - 有 artifact 但值不对 → 错改。
   - 0 分 + reason 说"轨迹为空" → 这是 bug(轨迹 schema 没对齐,看上一节),不是 agent 的问题,去修 generate 的 trajectories。
4. **reason**:`per-case 产物文件每条 `reason` 要有信息量(指名漏改/错改/多改了哪个字段),不能只写 "correct"/"incorrect";文案应来自项目既有 eval pipeline(evaluator 的 failure_detail / LLM scorer/judge 判语),别自己造空泛 fallback。

任何一项"没有" → 先分清:是真该没有(case 本来就没产 artifact,reason 写 "missing_output" 是对的)还是你的 bug(如:轨迹空但其实 messages 有内容 / reason 是空泛 fallback 但项目 eval 里其实写了原因没被读到)。是 bug 就修项目 eval 的参数 / trajectories schema / reason 取值来源,再重跑冒烟。**修好再给用户看,别把坏产物交出去确认。**

## 冒烟(产物按『通用约定』放 `<smoke dir>`,保留不清)

> **冒烟必须真跑 agent(不带 `--dry-run`)** —— 输出的 `predictions.jsonl` / `trajectories.jsonl` / `workspace artifacts` 要是真实数据,不是合成的;这些数据后面要给用户看(确认格式)还要给后续写 AntOmniEvo System + Evaluator 模块时参考(解析它们的字段)。合成的数据没参考价值。
>
> 所以冒烟前先跟用户确认:
> 1. **output dir** 按『通用约定』= `<smoke dir>`(`<workspace>/tests/bootstrap_smoke/`),记 NOTES。
> 2. **model key** 准备好了吗(如果有):agent import 时就 build 模型,没 key 真跑不了。
> 没准备好 model key 就先停,等用户准备好再跑。

### A. generate 真跑 1 case(产真预测 + 真轨迹)
先按上面"选运行路径"判 agent 是只读型还是写型 ↓

**只读型**(产物是纯检索/推理回答):
```
LOCAL_WORKSPACE=1 <model-key-env>=<key> python scripts/generate.py \
  --agent-src <步骤3.1 module> --cases <test> --output-dir <smoke dir>/gen --limit 1
```
**写型**(产物是 config/source edit / release ticket 等 —— 要 sandbox-transport + 项目源码仓库):
```
<model-key-env>=<key> python scripts/generate.py \
  --agent-src <步骤3.1 module> --cases <test> --output-dir <smoke dir>/gen --limit 1 \
  --local-sandbox-transport --local-source-repo <项目源码仓库 checkout>
```
(写型 agent 用 MCP 时,MCP 身份 token + 权限也要先就绪 —— 见上坑。)
验证:
- `status` ∈ {completed, awaiting}(awaiting 是 HITL 停点不算失败),不是 dry_run / error / timeout
- **`predictions.jsonl` 的 `prediction_present=True`** + 有真实 `artifact`(不是合成)—— 写型卡在这=运行前置没备齐
- `trajectories.jsonl` 有真实消息流(`messages` 非空,有 tool_calls / tool_results)
- `run_summary.json` 的 `agent_file` 是真实路径
- workspace artifacts.jsonl 有真实工具产物

### B. evaluate 闭环(拿 A 的产物跑 evaluate)
```
python scripts/evaluate.py \
  --predictions <smoke dir>/gen/predictions.jsonl --cases <test> \
  --output <smoke dir>/eval [按步骤 4 跟用户对齐的 eval 参数]
```
- **先跑快的(无 LLM)那档**确认"产物对不对",要多维(含 LLM judge 之类)再跑全档(需 model key + 更久);具体档位/flag **以项目 eval CLI 为准**,别套别的项目的 stage 名。
- eval 某阶段若报"缺字段"(generate 把该信息放在 case context 文本里、没进 eval 要的结构化字段),看项目 eval 是否支持"复用预建中间产物"之类的 flag 跳过该阶段,或用带结构化字段的 cases;**具体字段名/flag 问用户**。
验证:
- summary 产物的 `score` 合理(0/1 都要看 reason 确认真值,见自查;不是必须 1.0 —— 看 case 难度)
- per-case 产物每条 `reason` 非空、有诊断价值(不是只写 "correct")
- 项目 eval 产出的全部中间产物保留(summary / per-case 结果 / 报告等,后续写 System/Evaluator 要照这些字段)
- 给用户看这些文件 → 用户确认格式对不对 → 确认后继续

### C. generate load-spec 真跑(验证候选 spec 载入)
```
LOCAL_WORKSPACE=1 <model-key-env>=<key> python scripts/generate.py \
  --agent-src <module> --spec-dir <cand> --editable <entry1> --editable <entry2> \
  --cases <test> --output-dir <smoke dir>/load --limit 1
```
验证:`spec_loaded=true` + `agent_file` 落在 tmp checkout 里 + `status=completed` + `trajectories.jsonl` 有内容。
